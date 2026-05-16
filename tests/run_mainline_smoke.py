from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = REPO_ROOT / "tests"


REQUIRED_SMOKES = [
    ("tool layer smoke", "run_tool_layer_smoke.py"),
    ("scheduler smoke", "run_scheduler_smoke.py"),
    ("runtime smoke", "run_runtime_smoke.py"),
    ("document task smoke", "run_document_task_smoke.py"),
    ("document flow showcase smoke", "run_document_flow_showcase_smoke.py"),
    ("document pipeline identity smoke", "run_document_pipeline_identity_smoke.py"),
    ("requirement demo smoke", "run_requirement_demo_smoke.py"),
    ("execution demo smoke", "run_execution_demo_smoke.py"),
    ("semantic task smoke", "run_semantic_task_smoke.py"),
    ("implementation-proof smoke", "run_implementation_proof_smoke.py"),
    ("full-build-demo smoke", "run_full_build_demo_smoke.py"),
]


OPTIONAL_SMOKES = [
    ("agent loop smoke", "run_agent_loop_smoke.py"),
    ("executor smoke", "run_executor_smoke.py"),
]


def safe_print(text: object = "") -> None:
    value = str(text or "")
    try:
        print(value)
        return
    except UnicodeEncodeError:
        pass

    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    sanitized = value.encode(encoding, errors="replace").decode(encoding, errors="replace")
    print(sanitized)


def smoke_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def run_process(script_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=smoke_env(),
    )


def main() -> int:
    safe_print("[mainline-smoke] starting")
    safe_print(f"[repo] {REPO_ROOT}")

    pass_count = 0
    fail_count = 0
    missing_required = 0
    skip_optional = 0
    passed_labels: list[str] = []
    failed_labels: list[str] = []
    skipped_labels: list[str] = []

    for label, filename in REQUIRED_SMOKES:
        script_path = TESTS_DIR / filename
        safe_print(f"[RUN] {label}: {filename}")
        if not script_path.exists():
            safe_print(f"[FAIL] {label}")
            safe_print("STDOUT:")
            safe_print("")
            safe_print("STDERR:")
            safe_print(f"required smoke missing: {script_path}")
            fail_count += 1
            missing_required += 1
            failed_labels.append(label)
            continue

        result = run_process(script_path)
        if result.returncode == 0:
            safe_print(f"[PASS] {label}")
            pass_count += 1
            passed_labels.append(label)
            continue

        safe_print(f"[FAIL] {label}")
        safe_print("STDOUT:")
        safe_print(result.stdout.rstrip())
        safe_print("")
        safe_print("STDERR:")
        safe_print(result.stderr.rstrip())
        fail_count += 1
        failed_labels.append(label)

    for label, filename in OPTIONAL_SMOKES:
        script_path = TESTS_DIR / filename
        safe_print(f"[RUN] {label}: {filename}")
        if not script_path.exists():
            safe_print(f"[SKIP] {label} (missing optional smoke)")
            skip_optional += 1
            skipped_labels.append(label)
            continue

        result = run_process(script_path)
        if result.returncode == 0:
            safe_print(f"[PASS] {label}")
            pass_count += 1
            passed_labels.append(label)
            continue

        safe_print(f"[FAIL] {label}")
        safe_print("STDOUT:")
        safe_print(result.stdout.rstrip())
        safe_print("")
        safe_print("STDERR:")
        safe_print(result.stderr.rstrip())
        fail_count += 1
        failed_labels.append(label)

    safe_print("")
    safe_print("[summary]")
    safe_print(f"pass: {pass_count}")
    safe_print(f"fail: {fail_count}")
    safe_print(f"missing_required: {missing_required}")
    safe_print(f"skip_optional: {skip_optional}")
    safe_print(f"passed_labels: {', '.join(passed_labels) if passed_labels else '-'}")
    safe_print(f"failed_labels: {', '.join(failed_labels) if failed_labels else '-'}")
    safe_print(f"skipped_labels: {', '.join(skipped_labels) if skipped_labels else '-'}")

    if fail_count == 0 and missing_required == 0:
        safe_print("[mainline-smoke] ALL PASS")
        return 0

    safe_print("[mainline-smoke] FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
