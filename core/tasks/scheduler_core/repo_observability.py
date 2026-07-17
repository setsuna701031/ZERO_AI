from __future__ import annotations

from typing import Any, Dict


def build_failure_observability_event(
    *,
    event_type: str,
    task: Dict[str, Any],
    task_id: str = "",
    error_text: str = "",
    status: str = "",
) -> Dict[str, Any]:
    task_payload = task if isinstance(task, dict) else {}
    resolved_task_id = str(
        task_id
        or task_payload.get("task_id")
        or task_payload.get("id")
        or task_payload.get("task_name")
        or ""
    ).strip()

    resolved_status = str(status or task_payload.get("status") or "").strip().lower()
    resolved_error = str(
        error_text
        or task_payload.get("last_error")
        or task_payload.get("failure_message")
        or ""
    ).strip()

    failure_type = str(
        task_payload.get("failure_type")
        or ("repo_task_failed" if resolved_status == "failed" else "repo_task_requeued")
    ).strip()

    event = {
        "event_type": str(event_type or "repo_task_failure"),
        "ok": False if resolved_status in {"failed", "error"} else True,
        "task_id": resolved_task_id,
        "status": resolved_status,
        "failure_type": failure_type,
        "error_text": resolved_error,
        "runtime_mode": "repo_state",
        "retry_count": int(task_payload.get("retry_count", 0) or 0),
        "replan_count": int(task_payload.get("replan_count", 0) or 0),
        "repair_fingerprint": str(task_payload.get("repair_fingerprint") or ""),
    }
    return event