from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from app import _l5_create_task_suggestion
from core.tasks.scheduler import Scheduler


class FakeSystem:
    def __init__(self, scheduler: Scheduler) -> None:
        self.scheduler = scheduler


def fail(message: str) -> int:
    print(f"[l5-trigger-l4-gate-smoke] FAIL: {message}")
    return 1


def assert_equal(actual: object, expected: object, label: str) -> int:
    if actual != expected:
        return fail(f"{label}: expected {expected!r}, got {actual!r}")
    print(f"[l5-trigger-l4-gate-smoke] PASS: {label}")
    return 0


def assert_true(value: Any, label: str) -> int:
    if not value:
        return fail(label)
    print(f"[l5-trigger-l4-gate-smoke] PASS: {label}")
    return 0


def main() -> int:
    print("[l5-trigger-l4-gate-smoke] START")

    workspace_dir = "workspace"
    output_path = os.path.join(workspace_dir, "shared", f"l5_direct_output_{int(time.time() * 1000)}.txt")
    scheduler = Scheduler(workspace_dir=workspace_dir, allow_commands=True)
    system = FakeSystem(scheduler)

    trigger_task = {
        "type": "write_file",
        "args": {
            "path": output_path,
            "content": "L5 must not write directly",
        },
    }

    result = _l5_create_task_suggestion(system, trigger_task)
    return validate_result(result, scheduler, output_path)


def validate_result(result: dict, scheduler: Scheduler, output_path: str) -> int:
    if not result.get("ok"):
        return fail(f"L5 suggestion create failed: {result}")

    task_id = str(result.get("task_id") or "")
    if not task_id:
        return fail("L5 suggestion did not return task_id")

    task = scheduler._get_task_from_repo(task_id)
    if not isinstance(task, dict):
        return fail("created L5 task candidate not found in scheduler repo")

    checks = [
        (result.get("submitted"), False, "L5 suggestion does not submit"),
        (result.get("queued"), False, "L5 suggestion does not queue"),
        (result.get("ran"), False, "L5 suggestion does not run"),
        (task.get("status"), "created", "task candidate remains created"),
        (task.get("requires_approval"), True, "task candidate requires approval"),
        (task.get("source"), "l5_world_trigger", "task candidate records L5 source"),
        (task.get("task_type"), "suggestion", "task candidate records suggestion type"),
    ]
    for actual, expected, label in checks:
        check = assert_equal(actual, expected, label)
        if check != 0:
            return check

    if os.path.exists(output_path):
        return fail("L5 trigger wrote output file directly")
    print("[l5-trigger-l4-gate-smoke] PASS: no direct file output")

    queue_snapshot = scheduler.get_queue_snapshot()
    ready_queue = queue_snapshot.get("ready_queue", [])
    check = assert_true(isinstance(ready_queue, list), "scheduler queue snapshot is available")
    if check != 0:
        return check
    if any(isinstance(item, dict) and item.get("task_id") == task_id for item in ready_queue):
        return fail("L5 task candidate was queued automatically")
    print("[l5-trigger-l4-gate-smoke] PASS: task candidate is not queued automatically")

    print("[l5-trigger-l4-gate-smoke] L4 gate PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
