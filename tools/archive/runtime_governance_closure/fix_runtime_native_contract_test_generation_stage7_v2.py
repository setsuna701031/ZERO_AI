from __future__ import annotations

"""Fix Stage 7 native contract test generation output.

Repairs generated tests that embedded JSON `null` in Python source and hardens
`tools/runtime_native_contract_test_generation_stage7.py` to render specs as
valid Python literals. This script does not modify runtime production code.
"""

import ast
import json
import pprint
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools" / "runtime_native_contract_test_generation_stage7.py"
TESTS_DIR = ROOT / "tests" / "runtime_contracts"
REPORT = ROOT / "docs" / "architecture" / "runtime_compatibility_inventory" / "runtime_native_contract_test_generation_stage7_fix_v2_report.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return proc.returncode, proc.stdout


def _patch_generator() -> bool:
    if not GENERATOR.exists():
        return False
    text = _read(GENERATOR)
    original = text

    # Add pprint import if the generator uses json.dumps to emit Python source.
    if "import pprint" not in text:
        text = text.replace("import json\n", "import json\nimport pprint\n", 1)
        if text == original and "from pathlib import Path" in text:
            text = text.replace("from pathlib import Path\n", "from pathlib import Path\nimport pprint\n", 1)

    # Replace common JSON rendering patterns with Python literal rendering.
    patterns = [
        (r"json\.dumps\(([^\n]+?),\s*indent=4,\s*sort_keys=True\)", r"pprint.pformat(\1, sort_dicts=False, width=120)"),
        (r"json\.dumps\(([^\n]+?),\s*indent=4\)", r"pprint.pformat(\1, sort_dicts=False, width=120)"),
        (r"json\.dumps\(([^\n]+?),\s*sort_keys=True\)", r"pprint.pformat(\1, sort_dicts=False, width=120)"),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)

    # If a helper variable named rendered_spec exists and still uses json.dumps, harden it.
    text = re.sub(
        r"rendered_spec\s*=\s*json\.dumps\(([^\n]+?)\)",
        r"rendered_spec = pprint.pformat(\1, sort_dicts=False, width=120)",
        text,
    )

    if text != original:
        _write(GENERATOR, text)
        return True
    return False


def _fix_generated_test_file(path: Path) -> int:
    text = _read(path)
    original = text

    # Convert JSON literals that are invalid in Python source.
    text = re.sub(r"(?<![A-Za-z0-9_])null(?![A-Za-z0-9_])", "None", text)
    text = re.sub(r"(?<![A-Za-z0-9_])true(?![A-Za-z0-9_])", "True", text)
    text = re.sub(r"(?<![A-Za-z0-9_])false(?![A-Za-z0-9_])", "False", text)

    if text != original:
        _write(path, text)
        return 1
    return 0


def _fix_generated_tests() -> int:
    if not TESTS_DIR.exists():
        return 0
    changed = 0
    for path in sorted(TESTS_DIR.glob("test_*_contracts.py")):
        changed += _fix_generated_test_file(path)
    return changed


def _compile_runtime_contract_tests() -> tuple[bool, str]:
    if not TESTS_DIR.exists():
        return False, f"missing tests dir: {TESTS_DIR}"
    returncode, output = _run([sys.executable, "-m", "compileall", "-q", str(TESTS_DIR)])
    return returncode == 0, output


def _pytest_runtime_contract_tests() -> tuple[bool, str]:
    returncode, output = _run([sys.executable, "-m", "pytest", "-q", str(TESTS_DIR)])
    return returncode == 0, output


def _pytest_smoke() -> list[tuple[str, bool, str]]:
    tests = [
        "tests/test_runtime_evidence_freeze.py",
        "tests/test_runtime_execution_ownership_migration_contract.py",
        "tests/test_runtime_mainline_freeze_contract.py",
        "tests/test_runtime_mode_propagation.py",
        "tests/test_runner_scheduler_boundary_survival.py",
    ]
    results: list[tuple[str, bool, str]] = []
    for test in tests:
        returncode, output = _run([sys.executable, "-m", "pytest", "-q", test])
        results.append((test, returncode == 0, output))
    return results


def _zero_patch_residue() -> list[str]:
    hits: list[str] = []
    for path in sorted((ROOT / "core").rglob("*.py")):
        try:
            text = _read(path)
        except UnicodeDecodeError:
            continue
        if "ZERO_PATCH_" in text:
            hits.append(str(path.relative_to(ROOT)))
    return hits


def main() -> int:
    patched_generator = _patch_generator()
    changed_tests = _fix_generated_tests()

    compile_ok, compile_output = _compile_runtime_contract_tests()
    contract_ok, contract_output = _pytest_runtime_contract_tests()
    smoke_results = _pytest_smoke()
    zero_patch = _zero_patch_residue()

    verification_passed = compile_ok and contract_ok and all(ok for _, ok, _ in smoke_results) and not zero_patch

    lines = [
        "# Runtime Native Contract Test Generation Stage 7 Fix V2",
        "",
        f"- patched generator: {patched_generator}",
        f"- generated test files changed: {changed_tests}",
        f"- ZERO_PATCH residue files: {len(zero_patch)}",
        f"- verification passed: {verification_passed}",
        "",
        "## Compile runtime_contracts",
        "```text",
        compile_output.strip(),
        "```",
        "",
        "## Pytest runtime_contracts",
        "```text",
        contract_output.strip(),
        "```",
        "",
        "## Smoke verification",
    ]
    for test, ok, output in smoke_results:
        lines.extend([f"### {'PASS' if ok else 'FAIL'}: `{test}`", "```text", output.strip(), "```", ""])
    if zero_patch:
        lines.extend(["## ZERO_PATCH residue", "```text", "\n".join(zero_patch), "```"])

    _write(REPORT, "\n".join(lines) + "\n")

    print(f"patched generator: {patched_generator}")
    print(f"generated test files changed: {changed_tests}")
    print(f"ZERO_PATCH residue: {len(zero_patch)}")
    print(f"report: {REPORT}")
    print("verification passed" if verification_passed else "verification failed")
    return 0 if verification_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
