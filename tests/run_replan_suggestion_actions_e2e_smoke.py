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
            "summary": "manual action recovery plan",
            "replan_count": int(task.get("replan_count", 0) or 0) + 1,
            "plan": {
                "task": "manual_action_recovery",
                "mode": "plan",
                "summary": "manual action recovery plan",
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


def fail(message: str) -> int:
    print(f"[replan-suggestion-actions-e2e-smoke] FAIL: {message}")
    return 1


def assert_equal(actual: object, expected: object, label: str) -> int:
    if actual != expected:
        return fail(f"{label}: expected {expected!r}, got {actual!r}")
    print(f"[replan-suggestion-actions-e2e-smoke] PASS: {label}")
    return 0


def command_to_replan_args(command: str) -> str:
    prefix = "task replan "
    if not command.startswith(prefix):
        raise ValueError(f"expected replan action command, got: {command}")
    return command[len(prefix):].strip()


def action_by_id(suggestion: Dict[str, Any], action_id: str) -> Dict[str, Any]:
    actions = suggestion.get("actions")
    if not isinstance(actions, list):
        raise ValueError("suggestion actions missing")
    for action in actions:
        if isinstance(action, dict) and action.get("id") == action_id:
            return action
    raise ValueError(f"action not found: {action_id}")


def make_failed_task() -> Dict[str, Any]:
    failed_step = {"type": "write_file", "path": "workspace/shared/action_flow.txt", "content": "OLD"}
    return {
        "task_id": "task_replan_action_flow",
        "task_name": "task_replan_action_flow",
        "goal": "manual replan action flow smoke",
        "status": "failed",
        "steps": [copy.deepcopy(failed_step)],
        "steps_total": 1,
        "current_step_index": 0,
        "replan_count": 0,
        "max_replans": 2,
        "replanned": False,
        "last_error": "write failed",
        "failure_message": "write failed",
        "last_step_result": {"ok": False, "step": copy.deepcopy(failed_step), "error": "write failed"},
        "results": [{"ok": False, "step": copy.deepcopy(failed_step), "step_index": 0, "error": "write failed"}],
        "execution_log": [],
    }


def main() -> int:
    print("[replan-suggestion-actions-e2e-smoke] START")

    task = make_failed_task()
    scheduler = Scheduler(workspace_dir="workspace", allow_commands=True)
    scheduler.replanner = FakeReplanner(
        [
            {"type": "write_file", "path": "workspace/shared/action_flow.txt", "content": "NEW"},
            {"type": "verify", "path": "workspace/shared/action_flow.txt", "contains": "NEW"},
        ]
    )
    system = FakeSystem(scheduler, task)

    public_record = scheduler._build_public_task_record(task)
    suggestion = public_record.get("replan_suggestion")
    if not isinstance(suggestion, dict):
        return fail("failed task did not expose replan_suggestion")

    checks = [
        (suggestion.get("would_replan"), True, "suggestion would_replan"),
        (suggestion.get("replanned"), False, "suggestion does not replan"),
        (suggestion.get("submitted"), False, "suggestion does not submit"),
        (suggestion.get("queued"), False, "suggestion does not queue"),
        (suggestion.get("ran"), False, "suggestion does not run"),
        (public_record.get("status"), "failed", "failed task remains failed before action"),
    ]
    for actual, expected, label in checks:
        check = assert_equal(actual, expected, label)
        if check != 0:
            return check

    preview_action = action_by_id(suggestion, "preview_replan")
    dry_run_action = action_by_id(suggestion, "dry_run_replan")
    approve_action = action_by_id(suggestion, "apply_replan")

    preview = _handle_replan_control(system, command_to_replan_args(str(preview_action.get("command") or "")))
    checks = [
        (preview.get("mode"), "replan_preview", "preview mode"),
        (preview.get("dry_run"), True, "preview is dry-run"),
        (preview.get("submitted"), False, "preview does not submit"),
        (preview.get("ran"), False, "preview does not run"),
        (preview.get("would_replan"), True, "preview would replan"),
    ]
    for actual, expected, label in checks:
        check = assert_equal(actual, expected, label)
        if check != 0:
            return check

    dry_run = _handle_replan_control(system, command_to_replan_args(str(dry_run_action.get("command") or "")))
    checks = [
        (dry_run.get("mode"), "replan_apply_dry_run", "dry-run mode"),
        (dry_run.get("dry_run"), True, "dry-run stays dry"),
        (dry_run.get("submitted"), False, "dry-run does not submit"),
        (dry_run.get("ran"), False, "dry-run does not run"),
        (dry_run.get("would_replan"), True, "dry-run would replan"),
    ]
    for actual, expected, label in checks:
        check = assert_equal(actual, expected, label)
        if check != 0:
            return check

    approved = _handle_replan_control(system, command_to_replan_args(str(approve_action.get("command") or "")))
    checks = [
        (approved.get("mode"), "replan_apply", "approve mode"),
        (approved.get("approved"), True, "manual approve accepted"),
        (approved.get("submitted"), True, "manual approve submitted"),
        (approved.get("queued"), True, "manual approve queued"),
        (approved.get("ran"), False, "manual approve does not run"),
    ]
    for actual, expected, label in checks:
        check = assert_equal(actual, expected, label)
        if check != 0:
            return check

    print("[replan-suggestion-actions-e2e-smoke] E2E PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
