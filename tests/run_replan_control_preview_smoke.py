from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from app import _handle_replan_control
from core.tasks.scheduler import Scheduler


class FakeReplanner:
    def __init__(self, steps: List[Dict[str, Any]]) -> None:
        self.steps = copy.deepcopy(steps)

    def create_replan_for_task(self, task: Dict[str, Any], user_input: str = "") -> Dict[str, Any]:
        return {
            "ok": True,
            "replanned": True,
            "summary": "manual preview recovery plan",
            "replan_count": int(task.get("replan_count", 0) or 0) + 1,
            "plan": {
                "task": "manual_preview_recovery",
                "mode": "plan",
                "summary": "manual preview recovery plan",
                "steps": copy.deepcopy(self.steps),
            },
        }


class FakeSystem:
    def __init__(self, scheduler: Scheduler, task: Dict[str, Any]) -> None:
        self.scheduler = scheduler
        self.task = task

    def get_task(self, task_id: str) -> Dict[str, Any]:
        if task_id == self.task.get("task_id"):
            return copy.deepcopy(self.task)
        return {"ok": False, "error": "task not found", "task_id": task_id}


def make_failed_task() -> Dict[str, Any]:
    step = {"type": "write_file", "path": "workspace/shared/manual_preview.txt", "content": "OLD"}
    return {
        "task_id": "task_manual_replan_preview",
        "task_name": "task_manual_replan_preview",
        "goal": "manual replan preview smoke",
        "status": "failed",
        "steps": [copy.deepcopy(step)],
        "steps_total": 1,
        "current_step_index": 0,
        "replan_count": 0,
        "max_replans": 2,
        "last_error": "write failed",
        "failure_message": "write failed",
        "last_step_result": {"ok": False, "step": copy.deepcopy(step), "error": "write failed"},
        "results": [{"ok": False, "step": copy.deepcopy(step), "step_index": 0, "error": "write failed"}],
        "execution_log": [],
    }


def fail(message: str) -> int:
    print(f"[replan-control-preview-smoke] FAIL: {message}")
    return 1


def assert_equal(actual: object, expected: object, label: str) -> int:
    if actual != expected:
        return fail(f"{label}: expected {expected!r}, got {actual!r}")
    print(f"[replan-control-preview-smoke] PASS: {label}")
    return 0


def main() -> int:
    print("[replan-control-preview-smoke] START")

    task = make_failed_task()
    scheduler = Scheduler(workspace_dir="workspace", allow_commands=True)
    scheduler.replanner = FakeReplanner(
        [
            {"type": "write_file", "path": "workspace/shared/manual_preview.txt", "content": "NEW"},
            {"type": "verify", "path": "workspace/shared/manual_preview.txt", "contains": "NEW"},
        ]
    )
    system = FakeSystem(scheduler, task)

    preview = _handle_replan_control(system, "preview task_manual_replan_preview")
    checks = [
        (preview.get("mode"), "replan_preview", "preview mode"),
        (preview.get("dry_run"), True, "preview is dry-run"),
        (preview.get("submitted"), False, "preview does not submit"),
        (preview.get("ran"), False, "preview does not run"),
        (preview.get("would_replan"), True, "preview reports would_replan"),
        (preview.get("preview_step_count"), 2, "preview reports candidate steps"),
    ]
    for actual, expected, label in checks:
        check = assert_equal(actual, expected, label)
        if check != 0:
            return check

    if task.get("status") != "failed" or task.get("replan_count") != 0:
        return fail("preview mutated source task")
    print("[replan-control-preview-smoke] PASS: preview leaves source task unchanged")

    dry_run = _handle_replan_control(system, "apply task_manual_replan_preview --dry-run")
    checks = [
        (dry_run.get("mode"), "replan_apply_dry_run", "apply dry-run mode"),
        (dry_run.get("dry_run"), True, "apply dry-run remains dry-run"),
        (dry_run.get("submitted"), False, "apply dry-run does not submit"),
        (dry_run.get("ran"), False, "apply dry-run does not run"),
    ]
    for actual, expected, label in checks:
        check = assert_equal(actual, expected, label)
        if check != 0:
            return check

    blocked = _handle_replan_control(system, "apply task_manual_replan_preview")
    checks = [
        (blocked.get("ok"), False, "apply without dry-run is blocked"),
        (blocked.get("mode"), "replan_apply", "blocked apply mode"),
        (blocked.get("submitted"), False, "blocked apply does not submit"),
        (blocked.get("ran"), False, "blocked apply does not run"),
    ]
    for actual, expected, label in checks:
        check = assert_equal(actual, expected, label)
        if check != 0:
            return check

    approved = _handle_replan_control(system, "apply task_manual_replan_preview --approve")
    checks = [
        (approved.get("mode"), "replan_apply", "approved apply mode"),
        (approved.get("approved"), True, "approved apply is approved"),
        (approved.get("submitted"), True, "approved apply submits to queue"),
        (approved.get("queued"), True, "approved apply queues task"),
        (approved.get("ran"), False, "approved apply does not run"),
        (approved.get("dry_run"), False, "approved apply is not dry-run"),
    ]
    for actual, expected, label in checks:
        check = assert_equal(actual, expected, label)
        if check != 0:
            return check

    print("[replan-control-preview-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
