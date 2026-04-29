from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.planning.replan_suggestion import build_replan_suggestion, format_replan_suggestion_cli
from core.tasks.scheduler import Scheduler


def fail(message: str) -> int:
    print(f"[replan-suggestion-smoke] FAIL: {message}")
    return 1


def assert_equal(actual: object, expected: object, label: str) -> int:
    if actual != expected:
        return fail(f"{label}: expected {expected!r}, got {actual!r}")
    print(f"[replan-suggestion-smoke] PASS: {label}")
    return 0


def main() -> int:
    print("[replan-suggestion-smoke] START")

    task = {
        "task_id": "task_demo_failed",
        "goal": "demo failed task",
        "status": "failed",
        "last_error": "demo failure",
        "replan_count": 0,
        "max_replans": 1,
    }

    suggestion = build_replan_suggestion(task)
    if not suggestion:
        return fail("failed task did not produce a suggestion")

    checks = [
        (suggestion.get("title"), "Replan available", "title"),
        (suggestion.get("message"), "Task failed. Replan available.", "message"),
        (suggestion.get("command"), "task replan preview task_demo_failed", "command"),
        (
            format_replan_suggestion_cli(suggestion),
            "Task failed. Replan available.\nUse:\ntask replan preview task_demo_failed",
            "cli text",
        ),
    ]
    for actual, expected, label in checks:
        check = assert_equal(actual, expected, label)
        if check != 0:
            return check

    scheduler = Scheduler(workspace_dir="workspace", allow_commands=True)
    public_record = scheduler._build_public_task_record(task)
    checks = [
        (public_record.get("replan_suggestion", {}).get("title"), "Replan available", "public record suggestion"),
        (len(public_record.get("suggestions", [])), 1, "public record suggestions list"),
        (
            public_record.get("cli_suggestion"),
            "Task failed. Replan available.\nUse:\ntask replan preview task_demo_failed",
            "public record cli text",
        ),
    ]
    for actual, expected, label in checks:
        check = assert_equal(actual, expected, label)
        if check != 0:
            return check

    exhausted = dict(task)
    exhausted["replan_count"] = 1
    if build_replan_suggestion(exhausted) is not None:
        return fail("exhausted task should not produce a suggestion")
    print("[replan-suggestion-smoke] PASS: exhausted task has no suggestion")

    print("[replan-suggestion-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
