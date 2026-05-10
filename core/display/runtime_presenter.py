from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from core.tasks.runtime_replay_narrative import build_runtime_replay_narrative


SUMMARY_FIELD_LIMIT = 220
DETAIL_FIELD_LIMIT = 360
COMPACT_FIELD_LIMIT = 180


def format_runtime_replay_summary(snapshot_or_narrative: Any) -> str:
    narrative = _ensure_narrative(snapshot_or_narrative)
    return "\n".join(
        [
            "Runtime Replay Summary:",
            f"- task_id: {_display(narrative.get('task_id'))}",
            f"- status: {_display(narrative.get('status'))}",
            f"- summary: {_display(narrative.get('summary'), SUMMARY_FIELD_LIMIT)}",
            f"- failure: {_display(narrative.get('failure_narrative'), SUMMARY_FIELD_LIMIT)}",
            f"- blocker: {_display(narrative.get('blocker_narrative'), SUMMARY_FIELD_LIMIT)}",
            f"- next_observation: {_display(narrative.get('next_observation'), SUMMARY_FIELD_LIMIT)}",
        ]
    )


def format_runtime_replay_detail(snapshot_or_narrative: Any) -> str:
    narrative = _ensure_narrative(snapshot_or_narrative)
    return "\n".join(
        [
            "Runtime Replay Detail:",
            f"- task_id: {_display(narrative.get('task_id'))}",
            f"- status: {_display(narrative.get('status'))}",
            f"- title: {_display(narrative.get('title'), SUMMARY_FIELD_LIMIT)}",
            f"- summary: {_display(narrative.get('summary'), DETAIL_FIELD_LIMIT)}",
            f"- timeline: {_display(narrative.get('timeline_narrative'), DETAIL_FIELD_LIMIT)}",
            f"- failure: {_display(narrative.get('failure_narrative'), DETAIL_FIELD_LIMIT)}",
            f"- blocker: {_display(narrative.get('blocker_narrative'), DETAIL_FIELD_LIMIT)}",
            f"- next_observation: {_display(narrative.get('next_observation'), DETAIL_FIELD_LIMIT)}",
        ]
    )


def format_runtime_replay_compact(snapshot_or_narrative: Any) -> str:
    """
    Human-readable compact replay view.

    This function intentionally does not change the existing narrative contract.
    It prefers structured snapshot fields over narrative strings so CLI output does
    not expose large nested raw payloads.
    """
    narrative = _ensure_narrative(snapshot_or_narrative)
    snapshot = _extract_snapshot(snapshot_or_narrative, narrative)

    task_id = _first_nonempty(
        _mapping_get(snapshot, "task_id"),
        narrative.get("task_id"),
        "",
    )
    status = _first_nonempty(
        _mapping_get(snapshot, "status"),
        narrative.get("status"),
        "unknown",
    )
    title = _first_nonempty(
        _mapping_get(snapshot, "goal"),
        _mapping_get(snapshot, "title"),
        narrative.get("title"),
        "task",
    )
    summary = _first_nonempty(
        _mapping_get(snapshot, "replay_summary"),
        narrative.get("summary"),
        f"{task_id or title} is {status}.",
    )

    failed_events = _list_or_empty(_mapping_get(snapshot, "failed_events"))
    blockers = _list_or_empty(_mapping_get(snapshot, "blockers"))
    timeline = _list_or_empty(_mapping_get(snapshot, "timeline"))
    latest_event = _mapping_or_empty(_mapping_get(snapshot, "latest_event"))

    failure_line = _summarize_failed_events(failed_events, status=status)
    blocker_line = _summarize_blockers(blockers, status=status)
    latest_line = _summarize_latest_event(latest_event, timeline)
    next_line = _build_structured_next_observation(
        status=status,
        failed_events=failed_events,
        blockers=blockers,
        latest_event=latest_event,
    )

    return "\n".join(
        [
            "Runtime Replay Compact:",
            f"- task_id: {_display(task_id)}",
            f"- status: {_display(status)}",
            f"- title: {_display(title, COMPACT_FIELD_LIMIT)}",
            f"- summary: {_display(summary, COMPACT_FIELD_LIMIT)}",
            f"- failure: {_display(failure_line, COMPACT_FIELD_LIMIT)}",
            f"- blocker: {_display(blocker_line, COMPACT_FIELD_LIMIT)}",
            f"- latest_event: {_display(latest_line, COMPACT_FIELD_LIMIT)}",
            f"- next_observation: {_display(next_line, COMPACT_FIELD_LIMIT)}",
        ]
    )


def _ensure_narrative(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping) and _looks_like_narrative(value):
        return {
            "task_id": _safe_str(value.get("task_id")),
            "status": _safe_str(value.get("status")) or "unknown",
            "title": _safe_str(value.get("title")) or "task",
            "summary": _safe_str(value.get("summary")) or "task is unknown with 0 replay event(s).",
            "timeline_narrative": _safe_str(value.get("timeline_narrative")) or "No replay timeline events are available.",
            "failure_narrative": _safe_str(value.get("failure_narrative")) or "No failed replay events were captured.",
            "blocker_narrative": _safe_str(value.get("blocker_narrative")) or "No blockers were captured.",
            "next_observation": _safe_str(value.get("next_observation")) or "Inspect the replay snapshot fields before deciding the next human action.",
            "raw_snapshot": value.get("raw_snapshot"),
        }
    return build_runtime_replay_narrative(value)


def _looks_like_narrative(value: Mapping[str, Any]) -> bool:
    return any(
        key in value
        for key in (
            "timeline_narrative",
            "failure_narrative",
            "blocker_narrative",
            "next_observation",
        )
    )


def _extract_snapshot(snapshot_or_narrative: Any, narrative: Mapping[str, Any]) -> Dict[str, Any]:
    if isinstance(snapshot_or_narrative, Mapping) and not _looks_like_narrative(snapshot_or_narrative):
        return dict(snapshot_or_narrative)

    raw_snapshot = narrative.get("raw_snapshot")
    if isinstance(raw_snapshot, Mapping):
        return dict(raw_snapshot)

    return {}


def _summarize_failed_events(failed_events: List[Any], *, status: str) -> str:
    events = [item for item in failed_events if isinstance(item, Mapping)]
    if not events:
        if _safe_str(status).lower() in {"failed", "error"}:
            return "Task is failed, but no structured failed event was captured."
        return "No failed replay events were captured."

    first = events[0]
    event_type = _first_nonempty(first.get("event_type"), first.get("type"), "failure")
    source = _first_nonempty(first.get("source"), "runtime")
    status_text = _first_nonempty(first.get("status"), "")
    summary = _first_nonempty(first.get("summary"), "")

    error = _extract_error_payload(first)
    error_type = _first_nonempty(
        _mapping_get(error, "type"),
        _mapping_get(error, "error_type"),
        _extract_type_token(summary),
        "",
    )
    message = _first_nonempty(
        _mapping_get(error, "message"),
        _mapping_get(error, "error"),
        _extract_message_token(summary),
        "",
    )
    classification = _first_nonempty(
        _mapping_get(error, "classification"),
        _deep_find_string(first, "classification"),
        "",
    )
    attempts = _first_nonempty(
        _mapping_get(error, "max_attempts"),
        _deep_find_string(first, "max_attempts"),
        _count_attempts(first),
        "",
    )

    detail_parts: List[str] = []
    if error_type:
        detail_parts.append(str(error_type))
    if message and message != error_type:
        detail_parts.append(str(message))
    if classification:
        detail_parts.append(f"classification={classification}")
    if attempts:
        detail_parts.append(f"attempts={attempts}")

    if not detail_parts:
        compact_summary = _compact_text(summary, max_len=120)
        if compact_summary:
            detail_parts.append(compact_summary)

    prefix = f"{len(events)} failed event(s). First: {source} {event_type}"
    if status_text:
        prefix += f" [{status_text}]"
    if detail_parts:
        prefix += "; " + ", ".join(detail_parts)
    return prefix + "."


def _summarize_blockers(blockers: List[Any], *, status: str) -> str:
    if not blockers:
        if _safe_str(status).lower() == "blocked":
            return "Task is blocked, but no structured blocker reason was captured."
        return "No blockers were captured."

    first = blockers[0]
    reason = _blocker_text(first)
    if len(blockers) == 1:
        return f"One blocker: {reason or 'unknown blocker'}."
    return f"{len(blockers)} blockers. First: {reason or 'unknown blocker'}."


def _summarize_latest_event(latest_event: Mapping[str, Any], timeline: List[Any]) -> str:
    event = latest_event if isinstance(latest_event, Mapping) and latest_event else {}
    if not event:
        timeline_events = [item for item in timeline if isinstance(item, Mapping)]
        if timeline_events:
            event = timeline_events[-1]
    if not event:
        return "No latest replay event was captured."

    source = _first_nonempty(event.get("source"), "runtime")
    event_type = _first_nonempty(event.get("event_type"), event.get("type"), "event")
    status = _first_nonempty(event.get("status"), "")
    summary = _first_nonempty(event.get("summary"), "")

    parts = [f"{source} {event_type}"]
    if status:
        parts.append(f"status={status}")

    action = _first_nonempty(
        _mapping_get(event, "action"),
        _deep_find_string(event, "action"),
        "",
    )
    if action:
        parts.append(f"action={action}")

    if summary and len(" ".join(parts)) < 120:
        parts.append(_compact_text(summary, max_len=80))

    return "; ".join(parts)


def _build_structured_next_observation(
    *,
    status: str,
    failed_events: List[Any],
    blockers: List[Any],
    latest_event: Mapping[str, Any],
) -> str:
    lowered = _safe_str(status).lower()
    if blockers:
        return "Review the blocker reason and related task state before taking action."

    if failed_events:
        first = failed_events[0] if isinstance(failed_events[0], Mapping) else {}
        error = _extract_error_payload(first)
        error_type = _first_nonempty(
            _mapping_get(error, "type"),
            _mapping_get(error, "error_type"),
            _deep_find_string(first, "type"),
            "failed event",
        )
        return f"Inspect execution_log.json and trace.json around {error_type} before deciding on a repair."

    if lowered in {"finished", "completed", "done", "success"}:
        return "Confirm the final output and verify the timeline matches the expected task flow."

    if lowered in {"running", "pending", "queued", "in_progress", "replanning"}:
        latest = _summarize_latest_event(latest_event, [])
        return f"Check whether the latest event is still progressing: {latest}."

    if lowered in {"failed", "error"}:
        return "Inspect the latest replay event, execution_log.json, and task error fields before repair."

    return "Inspect the replay snapshot fields before deciding the next human action."


def _extract_error_payload(event: Mapping[str, Any]) -> Dict[str, Any]:
    for key in ("error", "exception", "failure"):
        value = event.get(key)
        if isinstance(value, Mapping):
            return dict(value)

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

    result = event.get("result")
    if isinstance(result, Mapping):
        error = result.get("error")
        if isinstance(error, Mapping):
            return dict(error)

    return {}


def _blocker_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return _first_nonempty(
            value.get("reason"),
            value.get("blocked_reason"),
            value.get("message"),
            value.get("error"),
            value.get("type"),
        )
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


def _extract_type_token(text: Any) -> str:
    value = _safe_str(text)
    if "'type':" in value:
        marker = "'type':"
        tail = value.split(marker, 1)[1].strip()
        if tail.startswith("'"):
            return tail.split("'", 2)[1] if len(tail.split("'", 2)) >= 2 else ""
        return tail.split(",", 1)[0].strip(" {}")
    if '"type":' in value:
        marker = '"type":'
        tail = value.split(marker, 1)[1].strip()
        if tail.startswith('"'):
            return tail.split('"', 2)[1] if len(tail.split('"', 2)) >= 2 else ""
        return tail.split(",", 1)[0].strip(" {}")
    return ""


def _extract_message_token(text: Any) -> str:
    value = _safe_str(text)
    for marker, quote in (("'message':", "'"), ('"message":', '"')):
        if marker not in value:
            continue
        tail = value.split(marker, 1)[1].strip()
        if tail.startswith(quote):
            parts = tail.split(quote, 2)
            if len(parts) >= 2:
                return parts[1]
        return tail.split(",", 1)[0].strip(" {}")
    return ""


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
        text = _safe_str(value)
        if text:
            return text
    return ""


def _display(value: Any, max_len: int = SUMMARY_FIELD_LIMIT) -> str:
    text = _compact_text(value, max_len=max_len)
    return text if text else "<none>"


def _compact_text(value: Any, max_len: int = SUMMARY_FIELD_LIMIT) -> str:
    text = _safe_str(value)
    if not text:
        return ""
    text = " ".join(text.split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
