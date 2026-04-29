from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.planning.replan_suggestion import build_replan_suggestion
from core.tasks.scheduler import Scheduler


def fail(message: str) -> int:
    print(f"[auto-replan-suggestion-smoke] FAIL: {message}")
    return 1


def assert_equal(actual: object, expected: object, label: str) -> int:
    if actual != expected:
        return fail(f"{label}: expected {expected!r}, got {actual!r}")
    print(f"[auto-replan-suggestion-smoke] PASS: {label}")
    return 0


def main() -> int:
    print("[auto-replan-suggestion-smoke] START")

    failed_task = {
        "task_id": "task_auto_replan_suggestion",
        "goal": "auto suggestion only smoke",
        "status": "failed",
        "last_error": "verification failed",
        "replan_count": 0,
        "max_replans": 1,
        "replanned": False,
    }

    suggestion = build_replan_suggestion(failed_task)
    if not suggestion:
        return fail("failed task has no replan_suggestion")

    checks = [
        (suggestion.get("would_replan"), True, "would_replan"),
        (suggestion.get("replanned"), False, "replanned"),
        (suggestion.get("submitted"), False, "submitted"),
        (suggestion.get("queued"), False, "queued"),
        (suggestion.get("ran"), False, "ran"),
    ]
    for actual, expected, label in checks:
        check = assert_equal(actual, expected, label)
        if check != 0:
            return check

    scheduler = Scheduler(workspace_dir="workspace", allow_commands=True)
    public_record = scheduler._build_public_task_record(failed_task)
    public_suggestion = public_record.get("replan_suggestion")
    if not isinstance(public_suggestion, dict):
        return fail("public task record has no replan_suggestion")

    checks = [
        (public_suggestion.get("would_replan"), True, "public would_replan"),
        (public_suggestion.get("replanned"), False, "public replanned"),
        (public_suggestion.get("submitted"), False, "public submitted"),
        (public_suggestion.get("queued"), False, "public queued"),
        (public_suggestion.get("ran"), False, "public ran"),
        (public_record.get("replanned"), False, "task remains not replanned"),
        (public_record.get("status"), "failed", "task remains failed"),
    ]
    for actual, expected, label in checks:
        check = assert_equal(actual, expected, label)
        if check != 0:
            return check

    exhausted = dict(failed_task)
    exhausted["replan_count"] = 1
    if build_replan_suggestion(exhausted) is not None:
        return fail("replan-exhausted task should not suggest replan")
    print("[auto-replan-suggestion-smoke] PASS: exhausted task has no suggestion")

    print("[auto-replan-suggestion-smoke] L4 smoke PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
