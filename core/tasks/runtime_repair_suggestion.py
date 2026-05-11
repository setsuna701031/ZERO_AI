from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from core.tasks.runtime_state_hygiene import freeze_runtime_export


DEFAULT_INSPECTION_TARGETS = [
    "execution_log.json",
    "trace.json",
    "runtime_state.json",
]


def build_runtime_repair_suggestion(snapshot: Any) -> Dict[str, Any]:
    """Build a read-only repair suggestion from a runtime replay snapshot.

    This layer does not execute tools, write files, schedule tasks, or mutate the
    provided snapshot. It only derives an operator-facing recommendation from
    structured runtime state.
    """
    raw_snapshot = freeze_runtime_export(snapshot)
    safe_snapshot = snapshot if isinstance(snapshot, Mapping) else {}

    task_id = _first_nonempty(safe_snapshot.get("task_id"))
    status = _first_nonempty(safe_snapshot.get("status"), "unknown")
    failed_events = _list_or_empty(safe_snapshot.get("failed_events"))
    blockers = _list_or_empty(safe_snapshot.get("blockers"))
    latest_event = _mapping_or_empty(safe_snapshot.get("latest_event"))

    if blockers:
        reason = _blocker_text(blockers[0]) or "blocked task"
        return _suggestion(
            suggestion_type="blocked_task",
            severity="high",
            reason=reason,
            recommended_inspection=["runtime_state.json", "task_snapshot.json"],
            retry_recommended=False,
            human_summary=f"Task is blocked: {reason}. Resolve the blocker before retrying.",
            task_id=task_id,
            status=status,
            raw_snapshot=raw_snapshot,
        )

    if failed_events:
        return _suggest_from_failed_event(
            failed_events[0],
            failed_count=len([item for item in failed_events if isinstance(item, Mapping)]),
            task_id=task_id,
            status=status,
            raw_snapshot=raw_snapshot,
        )

    lowered = status.lower()
    if lowered in {"finished", "completed", "done", "success"}:
        return _suggestion(
            suggestion_type="no_repair_needed",
            severity="info",
            reason="task completed without structured failed events",
            recommended_inspection=["result.json", "runtime_state.json"],
            retry_recommended=False,
            human_summary="No repair is recommended. Confirm the final output and archive the runtime evidence if needed.",
            task_id=task_id,
            status=status,
            raw_snapshot=raw_snapshot,
        )

    if lowered in {"running", "pending", "queued", "replanning", "in_progress"}:
        latest = _event_label(latest_event) if latest_event else "latest runtime event"
        return _suggestion(
            suggestion_type="observe_running_task",
            severity="info",
            reason=f"task is still {status}",
            recommended_inspection=["runtime_state.json", "trace.json"],
            retry_recommended=False,
            human_summary=f"No repair is recommended yet. Observe {latest} and wait for a terminal state.",
            task_id=task_id,
            status=status,
            raw_snapshot=raw_snapshot,
        )

    if lowered in {"failed", "error"}:
        return _suggestion(
            suggestion_type="failed_without_event",
            severity="medium",
            reason="task is failed but no structured failed event was captured",
            recommended_inspection=DEFAULT_INSPECTION_TARGETS,
            retry_recommended=False,
            human_summary="Inspect execution_log.json and trace.json before deciding whether to retry or replan.",
            task_id=task_id,
            status=status,
            raw_snapshot=raw_snapshot,
        )

    return _suggestion(
        suggestion_type="insufficient_runtime_evidence",
        severity="low",
        reason="no failed events or blockers were captured",
        recommended_inspection=["runtime_state.json", "trace.json"],
        retry_recommended=False,
        human_summary="Insufficient runtime evidence for a repair recommendation. Inspect runtime state before taking action.",
        task_id=task_id,
        status=status,
        raw_snapshot=raw_snapshot,
    )


def build_runtime_repair_suggestions(snapshot: Any) -> List[Dict[str, Any]]:
    """Return a list wrapper for future multi-suggestion flows."""
    return [build_runtime_repair_suggestion(snapshot)]


def _suggest_from_failed_event(
    event: Any,
    *,
    failed_count: int,
    task_id: str,
    status: str,
    raw_snapshot: Any,
) -> Dict[str, Any]:
    safe_event = event if isinstance(event, Mapping) else {}
    action_type = _first_nonempty(
        safe_event.get("action_type"),
        safe_event.get("event_type"),
        safe_event.get("type"),
        "unknown_action",
    )
    status_text = _first_nonempty(safe_event.get("status"), "error")
    error = _extract_error_payload(safe_event)
    error_type = _first_nonempty(
        _mapping_get(error, "type"),
        _mapping_get(error, "error_type"),
        _deep_find_string(safe_event, "type"),
        "runtime_error",
    )
    message = _first_nonempty(
        _mapping_get(error, "message"),
        _mapping_get(error, "error"),
        _deep_find_string(safe_event, "message"),
        safe_event.get("summary"),
        "runtime failure",
    )
    classification = _first_nonempty(
        _mapping_get(error, "classification"),
        _deep_find_string(safe_event, "classification"),
    )
    attempts = _first_nonempty(
        _mapping_get(error, "max_attempts"),
        _deep_find_string(safe_event, "max_attempts"),
        _count_attempts(safe_event),
    )

    lowered_error = f"{error_type} {message} {classification}".lower()
    lowered_action = action_type.lower()

    if "python" in lowered_error or "run_python" in lowered_action:
        suggestion_type = "inspect_python_failure"
        severity = "high" if classification == "fatal" else "medium"
        retry_recommended = False if classification == "fatal" else _is_retryable(error, safe_event)
        inspection = ["execution_log.json", "trace.json", "runtime_state.json"]
        reason = _join_reason(error_type, message, classification, attempts)
        human = "Python execution failed. Inspect execution_log.json and trace.json around the failed run before repairing code or retrying."
    elif "verify" in lowered_action or "verification" in lowered_error:
        suggestion_type = "inspect_verification_failure"
        severity = "medium"
        retry_recommended = False
        inspection = ["execution_log.json", "result.json", "trace.json"]
        reason = _join_reason(error_type, message, classification, attempts)
        human = "Verification failed. Inspect expected vs actual output before retrying the task."
    elif "write" in lowered_action or "path" in lowered_error or "file" in lowered_error:
        suggestion_type = "inspect_file_operation_failure"
        severity = "medium"
        retry_recommended = _is_retryable(error, safe_event)
        inspection = ["execution_log.json", "runtime_state.json", "task_snapshot.json"]
        reason = _join_reason(error_type, message, classification, attempts)
        human = "A file operation likely failed. Inspect paths, guard output, and execution_log.json before retrying."
    elif "repair" in lowered_action:
        suggestion_type = "inspect_repair_attempt"
        severity = "medium"
        retry_recommended = False
        inspection = ["trace.json", "runtime_state.json", "execution_log.json"]
        reason = _join_reason(error_type, message, classification, attempts)
        human = "A repair attempt failed. Inspect the repair context and runtime trace before creating another repair task."
    else:
        suggestion_type = "inspect_runtime_failure"
        severity = "medium"
        retry_recommended = _is_retryable(error, safe_event)
        inspection = DEFAULT_INSPECTION_TARGETS
        reason = _join_reason(error_type, message, classification, attempts)
        human = "Runtime failure detected. Inspect execution_log.json and trace.json before deciding on retry or replan."

    if failed_count > 1:
        human = f"{human} {failed_count} failed event(s) were captured; start with the first failure."

    return _suggestion(
        suggestion_type=suggestion_type,
        severity=severity,
        reason=reason or f"{action_type} failed with status {status_text}",
        recommended_inspection=inspection,
        retry_recommended=retry_recommended,
        human_summary=human,
        task_id=task_id,
        status=status,
        raw_snapshot=raw_snapshot,
        failed_event={
            "action_type": action_type,
            "status": status_text,
            "error_type": error_type,
            "message": message,
            "classification": classification,
            "attempts": attempts,
        },
    )


def _suggestion(
    *,
    suggestion_type: str,
    severity: str,
    reason: str,
    recommended_inspection: List[str],
    retry_recommended: bool,
    human_summary: str,
    task_id: str,
    status: str,
    raw_snapshot: Any,
    failed_event: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "ok": True,
        "suggestion_type": suggestion_type,
        "severity": severity,
        "reason": reason,
        "recommended_inspection": list(recommended_inspection),
        "retry_recommended": bool(retry_recommended),
        "human_summary": human_summary,
        "task_id": task_id,
        "status": status,
        "raw_snapshot": raw_snapshot,
    }
    if failed_event is not None:
        payload["failed_event"] = failed_event
    return payload


def _extract_error_payload(event: Mapping[str, Any]) -> Dict[str, Any]:
    for key in ("error", "exception", "failure"):
        value = event.get(key)
        if isinstance(value, Mapping):
            return dict(value)

    result = event.get("result")
    if isinstance(result, Mapping):
        error = result.get("error")
        if isinstance(error, Mapping):
            return dict(error)

    raw = event.get("raw")
    if isinstance(raw, Mapping):
        for key in ("error", "exception", "failure"):
            value = raw.get(key)
            if isinstance(value, Mapping):
                return dict(value)
        result = raw.get("result")
        if isinstance(result, Mapping):
            error = result.get("error")
            if isinstance(error, Mapping):
                return dict(error)

    return {}


def _is_retryable(error: Mapping[str, Any], event: Mapping[str, Any]) -> bool:
    for value in (_mapping_get(error, "retryable"), _mapping_get(event, "retryable")):
        if isinstance(value, bool):
            return value
    classification = _first_nonempty(_mapping_get(error, "classification"), _deep_find_string(event, "classification")).lower()
    if classification in {"fatal", "blocked", "invalid"}:
        return False
    return False


def _join_reason(error_type: str, message: str, classification: str, attempts: str) -> str:
    parts: List[str] = []
    if error_type:
        parts.append(error_type)
    if message and message != error_type:
        parts.append(message)
    if classification:
        parts.append(f"classification={classification}")
    if attempts:
        parts.append(f"attempts={attempts}")
    return "; ".join(parts)


def _event_label(event: Mapping[str, Any]) -> str:
    return _first_nonempty(event.get("action_type"), event.get("event_type"), event.get("summary"), "runtime event")


def _blocker_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return _first_nonempty(value.get("reason"), value.get("blocked_reason"), value.get("message"), value.get("error"), value.get("type"))
    return ""


def _deep_find_string(data: Any, key: str, depth: int = 0) -> str:
    if depth > 6:
        return ""
    if isinstance(data, Mapping):
        value = data.get(key)
        if value not in (None, "", [], {}):
            if isinstance(value, (str, int, float, bool)):
                return str(value)
        for nested in data.values():
            found = _deep_find_string(nested, key, depth + 1)
            if found:
                return found
    if isinstance(data, list):
        for item in data:
            found = _deep_find_string(item, key, depth + 1)
            if found:
                return found
    return ""


def _count_attempts(data: Any) -> str:
    attempts = _deep_find_list(data, "attempts")
    if attempts is not None:
        return str(len(attempts))
    return ""


def _deep_find_list(data: Any, key: str, depth: int = 0) -> Optional[List[Any]]:
    if depth > 6:
        return None
    if isinstance(data, Mapping):
        value = data.get(key)
        if isinstance(value, list):
            return value
        for nested in data.values():
            found = _deep_find_list(nested, key, depth + 1)
            if found is not None:
                return found
    if isinstance(data, list):
        for item in data:
            found = _deep_find_list(item, key, depth + 1)
            if found is not None:
                return found
    return None


def _mapping_get(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)
    return None


def _mapping_or_empty(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _list_or_empty(value: Any) -> List[Any]:
    if isinstance(value, list):
        return list(value)
    return []


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
