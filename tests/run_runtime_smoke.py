from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = PROJECT_ROOT / "tests"

TEST_FILES = [
    "test_step_executor.py",
    "test_executor_repair_rules.py",
    "test_executor_safe_path_repair.py",
    "test_agent_loop.py",
]


def run_one(test_file: str) -> tuple[bool, int]:
    test_path = TESTS_DIR / test_file
    print("\n" + "=" * 100)
    print(f"RUN: {test_file}")
    print("=" * 100)

    result = subprocess.run(
        [sys.executable, str(test_path)],
        cwd=str(PROJECT_ROOT),
    )

    ok = result.returncode == 0

    print("-" * 100)
    print(f"RESULT: {test_file} -> {'PASS' if ok else 'FAIL'} (exit={result.returncode})")
    print("-" * 100)

    return ok, result.returncode


def main() -> None:
    print("\n[Runtime Smoke Runner]")
    print(f"project_root = {PROJECT_ROOT}")
    print(f"python       = {sys.executable}")

    passed = []
    failed = []

    for test_file in TEST_FILES:
        ok, code = run_one(test_file)
        if ok:
            passed.append(test_file)
        else:
            failed.append((test_file, code))

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"passed: {len(passed)}")
    for name in passed:
        print(f"  PASS - {name}")

    print(f"\nfailed: {len(failed)}")
    for name, code in failed:
        print(f"  FAIL - {name} (exit={code})")

    if failed:
        print("\nRUNTIME SMOKE: FAIL")
        raise SystemExit(1)

    print("\nRUNTIME SMOKE: PASS")
    raise SystemExit(0)


if __name__ == "__main__":
    main()