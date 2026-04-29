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
        "task_id": "task_display_replan_suggestion",
        "goal": "display replan suggestion smoke",
        "status": "failed",
        "last_error": "demo failure",
        "replan_count": 0,
        "max_replans": 1,
    }

    suggestion = build_replan_suggestion(task)
    if not suggestion:
        return fail("failed task did not produce display suggestion")

    expected_cli = (
        "Task failed. Replan available.\n"
        "Use:\n"
        "task replan preview task_display_replan_suggestion\n"
        "task replan apply task_display_replan_suggestion --dry-run\n"
        "task replan apply task_display_replan_suggestion --approve"
    )

    checks = [
        (suggestion.get("title"), "Replan available", "display title"),
        (suggestion.get("message"), "Task failed. Replan available.", "display message"),
        (suggestion.get("command"), "task replan preview task_display_replan_suggestion", "display command"),
        (suggestion.get("preview_command"), "task replan preview task_display_replan_suggestion", "preview command"),
        (suggestion.get("dry_run_command"), "task replan apply task_display_replan_suggestion --dry-run", "dry-run command"),
        (suggestion.get("apply_command"), "task replan apply task_display_replan_suggestion --approve", "apply command"),
        (len(suggestion.get("actions", [])), 3, "structured actions"),
        (format_replan_suggestion_cli(suggestion), expected_cli, "CLI display text"),
    ]
    for actual, expected, label in checks:
        check = assert_equal(actual, expected, label)
        if check != 0:
            return check

    scheduler = Scheduler(workspace_dir="workspace", allow_commands=True)
    public_record = scheduler._build_public_task_record(task)
    checks = [
        (public_record.get("replan_suggestion", {}).get("title"), "Replan available", "public title"),
        (public_record.get("replan_suggestion", {}).get("command"), "task replan preview task_display_replan_suggestion", "public command"),
        (public_record.get("replan_suggestion", {}).get("dry_run_command"), "task replan apply task_display_replan_suggestion --dry-run", "public dry-run command"),
        (public_record.get("replan_suggestion", {}).get("apply_command"), "task replan apply task_display_replan_suggestion --approve", "public apply command"),
        (public_record.get("cli_suggestion"), expected_cli, "public CLI display text"),
    ]
    for actual, expected, label in checks:
        check = assert_equal(actual, expected, label)
        if check != 0:
            return check

    print("[replan-suggestion-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
