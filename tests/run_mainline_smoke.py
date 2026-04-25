from __future__ import annotations

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


def run_process(script_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def main() -> int:
    print("[mainline-smoke] starting")
    print(f"[repo] {REPO_ROOT}")

    pass_count = 0
    fail_count = 0
    missing_required = 0
    skip_optional = 0

    for label, filename in REQUIRED_SMOKES:
        script_path = TESTS_DIR / filename
        print(f"[RUN] {label}: {filename}")
        if not script_path.exists():
            print(f"[FAIL] {label}")
            print("STDOUT:")
            print("")
            print("STDERR:")
            print(f"required smoke missing: {script_path}")
            fail_count += 1
            missing_required += 1
            continue

        result = run_process(script_path)
        if result.returncode == 0:
            print(f"[PASS] {label}")
            pass_count += 1
            continue

        print(f"[FAIL] {label}")
        print("STDOUT:")
        print(result.stdout.rstrip())
        print("")
        print("STDERR:")
        print(result.stderr.rstrip())
        fail_count += 1

    for label, filename in OPTIONAL_SMOKES:
        script_path = TESTS_DIR / filename
        print(f"[RUN] {label}: {filename}")
        if not script_path.exists():
            print(f"[SKIP] {label} (missing optional smoke)")
            skip_optional += 1
            continue

        result = run_process(script_path)
        if result.returncode == 0:
            print(f"[PASS] {label}")
            pass_count += 1
            continue

        print(f"[FAIL] {label}")
        print("STDOUT:")
        print(result.stdout.rstrip())
        print("")
        print("STDERR:")
        print(result.stderr.rstrip())
        fail_count += 1

    print("")
    print("[summary]")
    print(f"pass: {pass_count}")
    print(f"fail: {fail_count}")
    print(f"missing_required: {missing_required}")
    print(f"skip_optional: {skip_optional}")

    if fail_count == 0 and missing_required == 0:
        print("[mainline-smoke] ALL PASS")
        return 0

    print("[mainline-smoke] FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())