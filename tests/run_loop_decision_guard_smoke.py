from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.agent.loop_decision import observe_and_decide


def fail(message: str) -> int:
    print(f"[loop-decision-guard-smoke] FAIL: {message}")
    return 1


def assert_equal(actual: object, expected: object, label: str) -> int:
    if actual != expected:
        return fail(f"{label}: expected {expected!r}, got {actual!r}")
    print(f"[loop-decision-guard-smoke] PASS: {label}")
    return 0


def main() -> int:
    print("[loop-decision-guard-smoke] START")

    failed_result = {
        "ok": False,
        "status": "failed",
        "action": "step_failed",
        "error": "recoverable failure",
    }

    normal = observe_and_decide(
        failed_result,
        {"task_id": "guard_normal", "max_replans": 1, "replan_count": 0},
        max_replans=1,
        replan_count=0,
    )
    check = assert_equal(normal.get("decision"), "replan", "normal agent decision still allows replan")
    if check != 0:
        return check

    guarded = observe_and_decide(
        failed_result,
        {
            "task_id": "guard_task_loop",
            "decision_guard_mode": "task_loop",
            "max_replans": 1,
            "replan_count": 0,
        },
        max_replans=1,
        replan_count=0,
    )

    expectations = [
        (guarded.get("decision"), "fail", "task_loop replan is converted to fail"),
        (guarded.get("next_action"), "finish", "task_loop next_action is finish"),
        (guarded.get("terminal"), True, "task_loop decision is terminal"),
        (guarded.get("should_replan"), False, "task_loop should_replan is false"),
        (guarded.get("should_fail"), True, "task_loop should_fail is true"),
        (guarded.get("guarded"), True, "guard marker is present"),
        (guarded.get("guard_reason"), "replan_not_allowed_in_task_loop", "guard reason is explicit"),
    ]

    for actual, expected, label in expectations:
        check = assert_equal(actual, expected, label)
        if check != 0:
            return check

    original = guarded.get("original_decision")
    if not isinstance(original, dict):
        return fail("original_decision missing")
    check = assert_equal(original.get("decision"), "replan", "original replan decision is preserved")
    if check != 0:
        return check

    print("[loop-decision-guard-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
