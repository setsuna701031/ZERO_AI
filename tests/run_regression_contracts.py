from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REGRESSION_TESTS = [
    Path("tests/test_scheduler_parser_helpers.py"),
    Path("tests/test_runtime_execution_contracts.py"),
]


def run_test(test_path: Path) -> int:
    full_path = PROJECT_ROOT / test_path
    if not full_path.exists():
        print(f"[regression] MISSING: {test_path}")
        return 1

    print("=" * 80)
    print(f"[regression] RUN: {test_path}")
    print("=" * 80)

    result = subprocess.run(
        [sys.executable, str(full_path)],
        cwd=str(PROJECT_ROOT),
    )

    if result.returncode == 0:
        print(f"[regression] PASS: {test_path}")
    else:
        print(f"[regression] FAIL: {test_path}")

    return int(result.returncode)


def main() -> int:
    failures = 0

    for test_path in REGRESSION_TESTS:
        failures += 1 if run_test(test_path) != 0 else 0

    print("=" * 80)
    if failures:
        print(f"[regression] FAILED: {failures}/{len(REGRESSION_TESTS)} test files failed")
        return 1

    print(f"[regression] ALL PASS: {len(REGRESSION_TESTS)} test files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
