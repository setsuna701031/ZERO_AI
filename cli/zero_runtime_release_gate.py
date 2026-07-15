from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from typing import Iterable

from core.runtime.runtime_release_report import generate_runtime_release_report


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RELEASE_GATE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Runtime Invariants", ("tests/test_runtime_invariant_*.py", "tests/test_runtime_release_candidate.py")),
    ("Dashboard Tests", ("tests/test_runtime_operator_dashboard*.py", "tests/test_operator_dashboard_*.py", "tests/test_zero_dashboard*.py")),
    ("Goal Runtime Tests", ("tests/test_runtime_long_horizon_goal.py", "tests/test_runtime_goal_controller.py", "tests/test_long_horizon_goal_integration.py")),
    ("Goal Operations Tests", ("tests/test_runtime_goal_operations*.py", "tests/test_long_horizon_goal_operations_integration.py", "tests/test_zero_goal_operations_cli.py")),
    ("Daemon Tests", ("tests/test_runtime_goal_daemon*.py", "tests/test_long_horizon_goal_daemon_integration.py", "tests/test_zero_goal_daemon_cli.py")),
    ("Approval Tests", ("tests/test_runtime_operator_approval_gate.py", "tests/test_runtime_mission_execution_approval_flow.py", "tests/test_natural_language_mission_approval_execution_integration.py", "tests/test_zero_mission_approval_cli.py")),
    ("CLI Tests", ("tests/test_zero_agent_cli.py", "tests/test_zero_goal_cli.py", "tests/test_zero_mission_cli.py", "tests/test_zero_dashboard_cli.py", "tests/test_zero_dashboard_shutdown_cli.py")),
)


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    test_count: int
    detail: str = ""


def _expand(patterns: Iterable[str]) -> list[str]:
    files: set[Path] = set()
    for pattern in patterns:
        files.update(REPOSITORY_ROOT.glob(pattern))
    return [str(path.relative_to(REPOSITORY_ROOT)).replace("\\", "/") for path in sorted(files) if path.is_file()]


def run_release_gate() -> tuple[GateResult, ...]:
    results: list[GateResult] = []
    for name, patterns in RELEASE_GATE_GROUPS:
        tests = _expand(patterns)
        if not tests:
            results.append(GateResult(name, False, 0, "no_tests_selected"))
            continue
        process = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *tests],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        output = (process.stdout + process.stderr).strip()
        detail = output.splitlines()[-1] if output else "pytest_produced_no_summary"
        results.append(GateResult(name, process.returncode == 0, len(tests), detail))
    return tuple(results)


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="python -m cli.zero_runtime_release_gate",
        description="ZERO Runtime v1 RC focused release gate",
    )


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    report = generate_runtime_release_report(REPOSITORY_ROOT)
    results = run_release_gate()
    passed = all(result.passed for result in results)
    print("PASS" if passed else "FAIL")
    print("Release Gate Summary")
    print(f"Runtime Version: {report.runtime_version}")
    print(f"Git Commit: {report.git_commit}")
    for result in results:
        print(f"- {result.name}: {'PASS' if result.passed else 'FAIL'} ({result.test_count} files; {result.detail})")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["GateResult", "RELEASE_GATE_GROUPS", "build_parser", "main", "run_release_gate"]
