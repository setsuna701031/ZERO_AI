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

    command = f"task replan preview {task_id}"
    reason = _safe_text(task.get("last_error") or task.get("failure_message") or task.get("replan_summary"))

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
        "command": command,
        "primary_action": {
            "label": "Preview replan",
            "command": command,
        },
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
    command = _safe_text(suggestion.get("command"))
    if not command:
        return message

    return f"{message}\nUse:\n{command}"
