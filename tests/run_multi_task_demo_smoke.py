from __future__ import annotations

"""
Smoke: multi-task demo scenario

This smoke protects the demo-grade multi-task scenario.

It validates that:
- the demo script runs successfully,
- the demo reports PASS,
- the summary artifact is produced,
- the summary proves two normal tasks completed,
- the intentionally failing task did not block the normal tasks.

Run from project root:

    python tests/run_multi_task_demo_smoke.py
"""

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_SCRIPT = PROJECT_ROOT / "demos" / "demo_multi_task_scenario.py"
SUMMARY_PATH = PROJECT_ROOT / "workspace" / "shared" / "demo_multi_task_summary.txt"


def fail(message: str) -> int:
    print(f"[multi-task-demo-smoke] FAIL: {message}")
    return 1


def require_contains(text: str, needle: str, label: str) -> bool:
    if needle not in text:
        print(f"[multi-task-demo-smoke] missing {label}: {needle}")
        return False
    return True


def main() -> int:
    if not DEMO_SCRIPT.exists():
        return fail(f"demo script not found: {DEMO_SCRIPT}")

    completed = subprocess.run(
        [sys.executable, str(DEMO_SCRIPT)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""

    print(stdout, end="")
    if stderr.strip():
        print(stderr, end="" if stderr.endswith("\n") else "\n")

    if completed.returncode != 0:
        return fail(f"demo script returned {completed.returncode}")

    if "[multi-task-demo] PASS" not in stdout:
        return fail("demo stdout did not contain PASS marker")

    if not SUMMARY_PATH.exists():
        return fail(f"summary artifact not found: {SUMMARY_PATH}")

    summary = SUMMARY_PATH.read_text(encoding="utf-8", errors="replace")

    checks = [
        require_contains(summary, "ZERO multi-task demo summary", "summary title"),
        require_contains(summary, "[A-normal] PASS", "A task PASS"),
        require_contains(summary, "final_answer: MULTI_DEMO_A", "A final answer"),
        require_contains(summary, "[B-normal] PASS", "B task PASS"),
        require_contains(summary, "final_answer: MULTI_DEMO_B", "B final answer"),
        require_contains(summary, "[C-intentional-failure] PASS", "intentional failure PASS"),
        require_contains(summary, "overall: PASS", "overall PASS"),
    ]

    if not all(checks):
        return fail("summary artifact content check failed")

    print(f"[multi-task-demo-smoke] summary: {SUMMARY_PATH}")
    print("[multi-task-demo-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
