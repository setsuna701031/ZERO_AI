from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.tasks.scheduler import Scheduler


class FakeReplanner:
    def __init__(self, steps: List[Dict[str, Any]], *, replan_count: int = 1) -> None:
        self.steps = copy.deepcopy(steps)
        self.replan_count = replan_count

    def create_replan_for_task(self, task: Dict[str, Any], user_input: str = "") -> Dict[str, Any]:
        return {
            "ok": True,
            "replanned": True,
            "summary": "fake recovery plan",
            "replan_count": self.replan_count,
            "plan": {
                "task": "fake_recovery",
                "mode": "plan",
                "summary": "fake recovery plan",
                "steps": copy.deepcopy(self.steps),
            },
        }


def fail(message: str) -> int:
    print(f"[replan-safety-smoke] FAIL: {message}")
    return 1


def assert_equal(actual: object, expected: object, label: str) -> int:
    if actual != expected:
        return fail(f"{label}: expected {expected!r}, got {actual!r}")
    print(f"[replan-safety-smoke] PASS: {label}")
    return 0


def make_failed_task(steps: List[Dict[str, Any]], *, replan_count: int = 0, max_replans: int = 2) -> Dict[str, Any]:
    failed_step = copy.deepcopy(steps[0])
    return {
        "task_id": "replan_safety_task",
        "goal": "verify replan safety",
        "status": "failed",
        "steps": copy.deepcopy(steps),
        "steps_total": len(steps),
        "current_step_index": 0,
        "replan_count": replan_count,
        "max_replans": max_replans,
        "last_error": "write failed",
        "failure_message": "write failed",
        "last_step_result": {
            "ok": False,
            "step": failed_step,
            "error": "write failed",
        },
        "results": [
            {
                "ok": False,
                "step": failed_step,
                "step_index": 0,
                "error": "write failed",
            }
        ],
        "execution_log": [],
    }


def main() -> int:
    print("[replan-safety-smoke] START")

    original_steps = [
        {"type": "write_file", "path": "workspace/shared/demo.txt", "content": "OLD"},
    ]
    repaired_steps = [
        {"type": "write_file", "path": "workspace/shared/demo.txt", "content": "NEW"},
        {"type": "verify", "path": "workspace/shared/demo.txt", "contains": "NEW"},
    ]

    scheduler = Scheduler(workspace_dir="workspace", allow_commands=True)
    scheduler.replanner = FakeReplanner(repaired_steps, replan_count=1)
    suggested_task = make_failed_task(original_steps)
    suggested = scheduler._try_replan_task(suggested_task)
    checks = [
        (suggested.get("replanned"), False, "automatic path does not apply replan"),
        (suggested.get("would_replan"), True, "automatic path records replan suggestion"),
        (suggested.get("decision"), "suggested", "automatic path decision is suggested"),
        (suggested_task.get("status"), "failed", "automatic path leaves failed task failed"),
    ]
    for actual, expected, label in checks:
        check = assert_equal(actual, expected, label)
        if check != 0:
            return check

    accepted_task = make_failed_task(original_steps)
    accepted = scheduler.apply_replan_task(accepted_task)

    checks = [
        (accepted.get("replanned"), True, "new plan is accepted"),
        (accepted.get("decision"), "accepted", "accepted decision recorded"),
        (accepted_task.get("status"), "queued", "accepted task is queued"),
        (accepted_task.get("replan_count"), 1, "replan count increments"),
        (accepted.get("remaining_replans"), 1, "remaining budget is reported"),
    ]
    for actual, expected, label in checks:
        check = assert_equal(actual, expected, label)
        if check != 0:
            return check

    trace = accepted_task.get("replan_trace")
    if not isinstance(trace, list) or not any(item.get("outcome") == "accepted" for item in trace if isinstance(item, dict)):
        return fail("accepted replan trace missing")
    print("[replan-safety-smoke] PASS: accepted replan trace recorded")

    scheduler.replanner = FakeReplanner(repaired_steps, replan_count=2)
    repeated_task = make_failed_task(original_steps, replan_count=1, max_replans=3)
    repeated_task["replan_trace"] = copy.deepcopy(trace)
    repeated_task["steps"] = copy.deepcopy(repaired_steps)
    repeated_task["last_step_result"]["step"] = copy.deepcopy(repaired_steps[0])
    repeated_task["results"][0]["step"] = copy.deepcopy(repaired_steps[0])
    repeated = scheduler.apply_replan_task(repeated_task)

    checks = [
        (repeated.get("replanned"), False, "previously failed plan is rejected"),
        (repeated.get("decision"), "skipped", "repeated plan is skipped"),
        (repeated.get("summary"), "replanner returned equivalent steps", "equivalent bad plan is not restarted"),
    ]
    for actual, expected, label in checks:
        check = assert_equal(actual, expected, label)
        if check != 0:
            return check

    exhausted_task = make_failed_task(original_steps, replan_count=1, max_replans=1)
    exhausted = scheduler._try_replan_task(exhausted_task)
    checks = [
        (exhausted.get("replanned"), False, "budget-exhausted task is not replanned"),
        (exhausted.get("decision"), "skipped", "budget-exhausted task is skipped"),
        (exhausted.get("remaining_replans"), 0, "budget exhaustion reports zero remaining"),
    ]
    for actual, expected, label in checks:
        check = assert_equal(actual, expected, label)
        if check != 0:
            return check

    print("[replan-safety-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
