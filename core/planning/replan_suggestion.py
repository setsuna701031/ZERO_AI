from __future__ import annotations

from typing import Any, Dict, List, Optional


FAILED_STATUSES = {"failed", "error"}


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def build_replan_suggestion(task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Build a manual replan suggestion for failed tasks.

    This intentionally does not apply or resume a task. It only exposes the
    next safe manual command for CLI/UI surfaces.
    """
    if not isinstance(task, dict):
        return None

    status = _safe_text(task.get("status")).lower()
    if status not in FAILED_STATUSES:
        return None

    task_id = _safe_text(task.get("task_id") or task.get("task_name") or task.get("id"))
    if not task_id:
        return None

    replan_count = _safe_int(task.get("replan_count"), 0)
    max_replans = _safe_int(task.get("max_replans"), 1)
    remaining = max(0, max_replans - replan_count)
    if remaining <= 0:
        return None

    repairable = task.get("replan_repairable", None)
    if repairable is False:
        return None

    preview_command = f"task replan preview {task_id}"
    dry_run_command = f"task replan apply {task_id} --dry-run"
    apply_command = f"task replan apply {task_id} --approve"
    reason = _safe_text(task.get("last_error") or task.get("failure_message") or task.get("replan_summary"))
    primary_action = {
        "id": "preview_replan",
        "kind": "command",
        "label": "Preview replan",
        "command": preview_command,
        "destructive": False,
        "requires_approval": False,
    }
    apply_action = {
        "id": "dry_run_replan",
        "kind": "command",
        "label": "Dry-run replan",
        "command": dry_run_command,
        "destructive": False,
        "requires_approval": False,
    }
    approve_action = {
        "id": "apply_replan",
        "kind": "command",
        "label": "Apply replan",
        "command": apply_command,
        "destructive": False,
        "requires_approval": True,
    }

    return {
        "id": f"replan:{task_id}",
        "kind": "replan",
        "trigger": "task_failed",
        "title": "Replan available",
        "message": "Task failed. Replan available.",
        "would_replan": True,
        "replanned": False,
        "submitted": False,
        "queued": False,
        "ran": False,
        "command": preview_command,
        "preview_command": preview_command,
        "dry_run_command": dry_run_command,
        "apply_command": apply_command,
        "primary_action": primary_action,
        "secondary_actions": [apply_action, approve_action],
        "actions": [primary_action, apply_action, approve_action],
        "task_id": task_id,
        "reason": reason,
        "replan_count": replan_count,
        "max_replans": max_replans,
        "remaining_replans": remaining,
    }


def build_replan_suggestions(task: Dict[str, Any]) -> List[Dict[str, Any]]:
    suggestion = build_replan_suggestion(task)
    return [suggestion] if suggestion else []


def format_replan_suggestion_cli(suggestion: Optional[Dict[str, Any]]) -> str:
    if not isinstance(suggestion, dict):
        return ""

    message = _safe_text(suggestion.get("message")) or "Task failed. Replan available."
    commands: List[str] = []
    actions = suggestion.get("actions")
    if isinstance(actions, list):
        for action in actions:
            if not isinstance(action, dict):
                continue
            command = _safe_text(action.get("command"))
            if command and command not in commands:
                commands.append(command)

    fallback_command = _safe_text(suggestion.get("command"))
    if fallback_command and fallback_command not in commands:
        commands.insert(0, fallback_command)

    if not commands:
        return message

    return f"{message}\nUse:\n" + "\n".join(commands)
