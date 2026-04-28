# core/watch/auto_task_runner.py
"""
ZERO Auto Task Runner

Purpose:
- Product-facing helper for event-driven workflows.
- Polls ZERO task status.
- Finds queued tasks.
- Runs one queued task through the explicit bounded task loop:
    python app.py task loop <task_id> <max_cycles>

Why not use control_api.submit("Run task ...")?
- submit() creates a new semantic task.
- This runner must execute an existing queued task, not create another one.

Why subprocess?
- app.py already owns the stable CLI task-loop behavior.
- This avoids touching AgentLoop / Scheduler / Planner internals.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

from core.control.control_api import Zero


DEFAULT_POLL_SECONDS = 2.0
DEFAULT_MAX_CYCLES = 5


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _truncate_tail(text: Any, max_len: int = 1000) -> str:
    value = str(text or "")
    if len(value) <= max_len:
        return value
    return value[-max_len:]


def _extract_tasks(status_payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(status_payload, dict):
        return []
    tasks = status_payload.get("tasks")
    if not isinstance(tasks, list):
        return []
    return [task for task in tasks if isinstance(task, dict)]


def _extract_task_id(task: Dict[str, Any]) -> str:
    for key in ("task_id", "task_name", "id", "name"):
        value = _safe_str(task.get(key))
        if value:
            return value
    return ""


def _extract_status(task: Dict[str, Any]) -> str:
    return _safe_str(task.get("status")).lower()


def _is_queued(task: Dict[str, Any]) -> bool:
    """
    Accept both strict and display-form queued statuses.

    Some app/task-list outputs can expose status-like strings such as:
      - "queued"
      - "queued 0/3"
      - "queued 1/3"

    We treat any status containing the token "queued" as runnable.
    """
    status = _extract_status(task)
    return "queued" in status


def _is_terminal(task: Dict[str, Any]) -> bool:
    status = _extract_status(task)
    return any(token in status for token in ("finished", "completed", "failed", "canceled", "cancelled", "blocked"))


class AutoTaskRunner:
    def __init__(
        self,
        *,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
        max_cycles: int = DEFAULT_MAX_CYCLES,
        debug: bool = False,
    ) -> None:
        self.poll_seconds = max(0.2, float(poll_seconds))
        self.max_cycles = max(1, int(max_cycles))
        self.debug = bool(debug)
        self.zero = Zero()
        self.last_attempted_task_id = ""

    def find_queued_task(self) -> Optional[Dict[str, Any]]:
        status = self.zero.get_status()
        tasks = _extract_tasks(status)

        if self.debug:
            compact = [
                {
                    "task_id": _extract_task_id(task),
                    "status": _extract_status(task),
                    "goal": _safe_str(task.get("goal"))[:80],
                }
                for task in tasks[-10:]
            ]
            print("[auto_runner] status sample:", json.dumps(compact, ensure_ascii=False, indent=2, default=str))

        for task in tasks:
            if not _is_queued(task):
                continue
            if _is_terminal(task):
                continue

            task_id = _extract_task_id(task)
            if not task_id:
                continue

            # Avoid hammering the exact same stuck task every 2 seconds forever.
            # A different queued task can still run. Restarting the runner also clears this.
            if task_id == self.last_attempted_task_id:
                continue

            return task

        return None

    def run_task_loop(self, task_id: str) -> Dict[str, Any]:
        command = [
            sys.executable,
            "app.py",
            "task",
            "loop",
            task_id,
            str(self.max_cycles),
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
        )

        return {
            "ok": result.returncode == 0,
            "action": "task_loop",
            "task_id": task_id,
            "command": command,
            "returncode": result.returncode,
            "stdout": _truncate_tail(result.stdout),
            "stderr": _truncate_tail(result.stderr),
        }

    def run_once(self) -> Dict[str, Any]:
        task = self.find_queued_task()
        if not isinstance(task, dict):
            return {
                "ok": True,
                "action": "idle",
                "reason": "no queued task found",
            }

        task_id = _extract_task_id(task)
        if not task_id:
            return {
                "ok": False,
                "action": "invalid_task",
                "reason": "queued task has no task_id",
                "task": task,
            }

        self.last_attempted_task_id = task_id
        result = self.run_task_loop(task_id)

        return {
            "ok": bool(result.get("ok", False)),
            "action": "run_queued_task_loop",
            "task_id": task_id,
            "task": task,
            "result": result,
        }

    def run_forever(self) -> None:
        print("[auto_runner] started")
        print(f"[auto_runner] max_cycles: {self.max_cycles}")
        print("[auto_runner] press Ctrl+C to stop")

        while True:
            result = self.run_once()

            if self.debug or result.get("action") != "idle":
                print("[auto_runner]", json.dumps(result, ensure_ascii=False, indent=2, default=str))

            time.sleep(self.poll_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ZERO queued task auto runner")
    parser.add_argument("--poll-seconds", type=float, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--max-cycles", type=int, default=DEFAULT_MAX_CYCLES)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    runner = AutoTaskRunner(
        poll_seconds=args.poll_seconds,
        max_cycles=args.max_cycles,
        debug=args.debug,
    )

    if args.once:
        print(json.dumps(runner.run_once(), ensure_ascii=False, indent=2, default=str))
        return

    runner.run_forever()


if __name__ == "__main__":
    main()
