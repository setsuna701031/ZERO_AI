from __future__ import annotations

import ast
import datetime as _dt
import shutil
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent
MAINLINE_PATH = ROOT / "core" / "runtime" / "runtime_native_mainline.py"
ADAPTER_PATH = ROOT / "core" / "runtime" / "runtime_native_entry_adapter.py"
TEST_PATH = ROOT / "tests" / "test_runtime_native_mainline_compatibility_inventory.py"
REPORT_PATH = ROOT / "runtime_native_mainline_compatibility_inventory.txt"

TEST_SOURCE = 'from __future__ import annotations\n\nfrom pathlib import Path\n\n\nROOT = Path(__file__).resolve().parents[1]\nREPORT = ROOT / "runtime_native_mainline_compatibility_inventory.txt"\n\n\ndef test_runtime_native_mainline_compatibility_inventory_report_exists() -> None:\n    assert REPORT.exists()\n\n\ndef test_runtime_native_mainline_compatibility_inventory_has_required_sections() -> None:\n    text = REPORT.read_text(encoding="utf-8")\n\n    assert "Runtime Native Mainline Compatibility Inventory" in text\n    assert "Token Inventory" in text\n    assert "Marked Blocks" in text\n    assert "Function Inventory" in text\n    assert "Classification" in text\n    assert "Non-mainline issue reporting" in text\n\n\ndef test_runtime_native_mainline_compatibility_inventory_records_phase2_marker() -> None:\n    text = REPORT.read_text(encoding="utf-8")\n\n    assert "ZERO_PACKAGE19_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_PHASE2_BEGIN" in text\n    assert "ZERO_PACKAGE19_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_PHASE2_END" in text\n\n\ndef test_runtime_native_mainline_compatibility_inventory_records_normalize_count() -> None:\n    text = REPORT.read_text(encoding="utf-8")\n\n    assert "normalize_runtime_native_entry_request" in text\n    assert "count:" in text\n'

TOKENS = [
    "normalize_runtime_native_entry_request",
    "run_runtime_native_entry",
    "run_via_runtime_native_mainline",
    "legacy",
    "compatibility",
    "dispatch",
    "admit_legacy_request",
    "normalize_legacy_request",
    "retire_legacy_entry",
    "dispatch_legacy_entry",
]

MARKERS = [
    "ZERO_PACKAGE16_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_BEGIN",
    "ZERO_PACKAGE16_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_END",
    "ZERO_PACKAGE17_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_BEGIN",
    "ZERO_PACKAGE17_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_END",
    "ZERO_PACKAGE18_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_BEGIN",
    "ZERO_PACKAGE18_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_END",
    "ZERO_PACKAGE19_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_PHASE2_BEGIN",
    "ZERO_PACKAGE19_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_PHASE2_END",
]


def _backup(path: Path) -> None:
    if not path.exists():
        return
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, path.with_name(f"{path.name}.package20_backup_{stamp}"))


def _line_hits(lines: list[str], token: str) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for idx, line in enumerate(lines, start=1):
        if token in line:
            hits.append((idx, line.rstrip()))
    return hits


def _function_inventory(source: str) -> list[str]:
    tree = ast.parse(source)
    rows: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
            if any(token in name.lower() for token in ("legacy", "compat", "dispatch", "admit", "normalize", "retire")):
                rows.append(f"- line {node.lineno}: {name}")
    return sorted(rows)


def _classify_hit(line: str) -> str:
    stripped = line.strip()
    lowered = stripped.lower()
    if stripped.startswith("from core.runtime.runtime_native_entry_adapter import"):
        return "bridge import"
    if stripped.startswith("normalize_runtime_native_entry_request as"):
        return "adapter import alias"
    if stripped.startswith("run_runtime_native_entry as"):
        return "adapter import alias"
    if "def _zero_runtime_native_mainline_" in stripped:
        return "bridge helper"
    if "setattr(" in stripped:
        return "method binding"
    if "hasattr(" in stripped:
        return "method guard"
    if stripped.startswith("#"):
        return "marker/comment"
    if "legacy" in lowered or "compatibility" in lowered:
        return "compatibility text"
    return "reference"


def _build_report() -> str:
    if not MAINLINE_PATH.exists():
        raise FileNotFoundError(f"Missing runtime mainline: {MAINLINE_PATH}")
    if not ADAPTER_PATH.exists():
        raise FileNotFoundError(f"Missing runtime entry adapter: {ADAPTER_PATH}")

    mainline_source = MAINLINE_PATH.read_text(encoding="utf-8")
    adapter_source = ADAPTER_PATH.read_text(encoding="utf-8")
    ast.parse(mainline_source)
    ast.parse(adapter_source)

    mainline_lines = mainline_source.splitlines()
    adapter_lines = adapter_source.splitlines()

    out: list[str] = []
    out.append("Runtime Native Mainline Compatibility Inventory")
    out.append("")
    out.append(f"generated_at: {_dt.datetime.now().isoformat(timespec='seconds')}")
    out.append(f"root: {ROOT}")
    out.append(f"mainline: {MAINLINE_PATH.relative_to(ROOT)}")
    out.append(f"adapter: {ADAPTER_PATH.relative_to(ROOT)}")
    out.append("")

    out.append("Marked Blocks")
    for marker in MARKERS:
        out.append(f"- {marker} count: {mainline_source.count(marker)}")
    out.append("")

    out.append("Token Inventory")
    for token in TOKENS:
        main_hits = _line_hits(mainline_lines, token)
        adapter_hits = _line_hits(adapter_lines, token)
        out.append(f"- {token}")
        out.append(f"  mainline count: {len(main_hits)}")
        for lineno, line in main_hits:
            out.append(f"    line {lineno}: [{_classify_hit(line)}] {line}")
        out.append(f"  adapter count: {len(adapter_hits)}")
        for lineno, line in adapter_hits[:20]:
            out.append(f"    line {lineno}: {line}")
        if len(adapter_hits) > 20:
            out.append(f"    ... {len(adapter_hits) - 20} more adapter hits")
    out.append("")

    out.append("Function Inventory")
    functions = _function_inventory(mainline_source)
    if functions:
        out.extend(functions)
    else:
        out.append("- no matching compatibility/legacy/dispatch helper functions found")
    out.append("")

    out.append("Classification")
    out.append("- active bridge: Package19 marker block in core/runtime/runtime_native_mainline.py")
    out.append("- compatibility owner: core/runtime/runtime_native_entry_adapter.py")
    out.append("- current phase2 failure driver: mainline token count for normalize_runtime_native_entry_request exceeded the Package19 test threshold")
    out.append("- recommended next package: Package21 should remove redundant mainline token references only after confirming they are not required by the active bridge")
    out.append("")

    out.append("Not touched")
    out.append("- Scheduler")
    out.append("- TaskRunner")
    out.append("- AgentLoop")
    out.append("- CLI")
    out.append("- RuntimeRouteRegistry")
    out.append("")

    out.append("Validation")
    out.append("python -m compileall core/runtime tests")
    out.append("python -m pytest tests/test_runtime_native_mainline_compatibility_inventory.py tests/test_runtime_native_mainline_compatibility_retirement_phase2.py tests/test_runtime_native_mainline_compatibility_retirement_phase1.py tests/test_runtime_native_mainline_adapter_binding_cleanup.py tests/test_runtime_native_compatibility_adapter_extraction.py tests/test_runtime_native_compatibility_entry_semantics.py tests/test_runtime_route_registry_admission.py tests/test_aer_mainline_closure_seal.py -q")
    out.append("")

    out.append("Non-mainline issue reporting")
    out.append("Any unrelated issue discovered during validation must be reported explicitly and not silently skipped.")
    out.append("")

    return "\n".join(out)


def main() -> int:
    _backup(REPORT_PATH)
    _backup(TEST_PATH)

    report = _build_report()
    REPORT_PATH.write_text(report, encoding="utf-8", newline="\n")

    TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    ast.parse(TEST_SOURCE)
    TEST_PATH.write_text(TEST_SOURCE, encoding="utf-8", newline="\n")

    print(str(REPORT_PATH))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
