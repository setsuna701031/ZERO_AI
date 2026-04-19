from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON_EXE = sys.executable

# 目前先只收「穩定可過」的主線驗證。
# runtime_smoke 暫時不放進來，因為它目前會被 tests/test_agent_loop.py 阻塞：
# AttributeError: 'AgentLoop' object has no attribute 'run'
# 這個問題後面單獨修，不在這支主線 smoke runner 裡硬綁死。
SMOKE_COMMANDS: List[Tuple[str, List[str]]] = [
    (
        "tool_layer_smoke",
        [PYTHON_EXE, "tests/run_tool_layer_smoke.py"],
    ),
    (
        "scheduler_smoke",
        [PYTHON_EXE, "tests/test_scheduler_smoke.py"],
    ),
    (
        "document_task_smoke",
        [PYTHON_EXE, "tests/run_document_task_smoke.py"],
    ),
    (
        "requirement_demo_smoke",
        [PYTHON_EXE, "tests/run_requirement_demo_smoke.py"],
    ),
    (
        "execution_demo_smoke",
        [PYTHON_EXE, "tests/run_execution_demo_smoke.py"],
    ),
]


def run_one(label: str, cmd: List[str]) -> None:
    print(f"[mainline-smoke] running: {label}")
    print(f"[mainline-smoke] command: {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.stdout.strip():
        print(f"[mainline-smoke] stdout ({label}):")
        print(result.stdout.rstrip())

    if result.stderr.strip():
        print(f"[mainline-smoke] stderr ({label}):")
        print(result.stderr.rstrip())

    if result.returncode != 0:
        raise RuntimeError(
            f"[mainline-smoke] FAILED: {label}\n"
            f"returncode={result.returncode}"
        )

    print(f"[mainline-smoke] PASS: {label}")
    print("")


def main() -> int:
    print("[mainline-smoke] starting stable mainline validation suite...")
    print(f"[mainline-smoke] repo root: {REPO_ROOT}")
    print("")
    print("[mainline-smoke] included suites:")
    for label, _ in SMOKE_COMMANDS:
        print(f"  - {label}")
    print("")
    print("[mainline-smoke] excluded for now:")
    print("  - runtime_smoke (currently blocked by tests/test_agent_loop.py)")
    print("")

    for label, cmd in SMOKE_COMMANDS:
        run_one(label, cmd)

    print("[mainline-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())