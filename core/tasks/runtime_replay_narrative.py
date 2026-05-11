from __future__ import annotations

from typing import Any, Dict, List, Mapping

from core.tasks.runtime_state_hygiene import freeze_runtime_export


MAX_TIMELINE_EVENTS = 4


def build_runtime_replay_narrative(snapshot: Any) -> Dict[str, Any]:
    raw_snapshot = freeze_runtime_export(snapshot)
    safe_snapshot = snapshot if isinstance(snapshot, Mapping) else {}

    task_id = _first_nonempty(safe_snapshot.get("task_id"))
    status = _first_nonempty(safe_snapshot.get("status"), "unknown")
    title = _first_nonempty(safe_snapshot.get("goal"), safe_snapshot.get("title"), task_id, "task")
    timeline = safe_snapshot.get("timeline") if isinstance(safe_snapshot.get("timeline"), list) else []
    failed_events = safe_snapshot.get("failed_events") if isinstance(safe_snapshot.get("failed_events"), list) else []
    blockers = _extract_blockers(safe_snapshot)
    latest_event = safe_snapshot.get("latest_event") if isinstance(safe_snapshot.get("latest_event"), Mapping) else {}

    return {
        "task_id": task_id,
        "status": status,
        "title": title,
        "summary": _build_summary(task_id=task_id, status=status, title=title, timeline=timeline, failed_events=failed_events, blockers=blockers),
        "timeline_narrative": _build_timeline_narrative(timeline),
        "failure_narrative": _build_failure_narrative(failed_events, status=status),
        "blocker_narrative": _build_blocker_narrative(blockers, status=status),
        "next_observation": _build_next_observation(status=status, blockers=blockers, failed_events=failed_events, latest_event=latest_event),
        "raw_snapshot": raw_snapshot,
    }


def _build_summary(
    *,
    task_id: str,
    status: str,
    title: str,
    timeline: List[Any],
    failed_events: List[Any],
    blockers: List[str],
) -> str:
    subject = task_id or title or "task"
    event_count = len([item for item in timeline if isinstance(item, Mapping)])
    parts = [f"{subject} is {status or 'unknown'} with {event_count} replay event(s)."]
    if failed_events:
        parts.append(f"{len(failed_events)} event(s) need attention.")
    if blockers:
        parts.append(f"Primary blocker: {blockers[0]}.")
    return " ".join(parts)


def _build_timeline_narrative(timeline: List[Any]) -> str:
    events = [item for item in timeline if isinstance(item, Mapping)]
    if not events:
        return "No replay timeline events are available."

    selected = events[:MAX_TIMELINE_EVENTS]
    phrases = []
    for item in selected:
        index = item.get("sequence_index")
        label = f"{index}" if isinstance(index, int) else "?"
        source = _first_nonempty(item.get("source"), "unknown")
        event_type = _first_nonempty(item.get("event_type"), "unknown_event")
        summary = _first_nonempty(item.get("summary"), event_type)
        phrases.append(f"{label}. {source} {event_type}: {summary}")

    if len(events) > len(selected):
        phrases.append(f"... {len(events) - len(selected)} more event(s) omitted.")
    return " | ".join(phrases)


def _build_failure_narrative(failed_events: List[Any], *, status: str) -> str:
    events = [item for item in failed_events if isinstance(item, Mapping)]
    if not events:
        if status.lower() in {"failed", "error"}:
            return "The task is marked failed, but no failed replay event was captured."
        return "No failed replay events were captured."

    first = events[0]
    summary = _first_nonempty(first.get("summary"), first.get("event_type"), "failure event")
    if len(events) == 1:
        return f"One replay event needs attention: {summary}."
    return f"{len(events)} replay events need attention. First issue: {summary}."


def _build_blocker_narrative(blockers: List[str], *, status: str) -> str:
    if blockers:
        if len(blockers) == 1:
            return f"One blocker is present: {blockers[0]}."
        return f"{len(blockers)} blockers are present. First blocker: {blockers[0]}."
    if status.lower() == "blocked":
        return "The task is marked blocked, but no blocker reason was captured."
    return "No blockers were captured."


def _build_next_observation(
    *,
    status: str,
    blockers: List[str],
    failed_events: List[Any],
    latest_event: Mapping[str, Any],
) -> str:
    lowered = status.lower()
    if blockers:
        return f"Review the blocker before taking action: {blockers[0]}."
    if failed_events:
        first = failed_events[0] if isinstance(failed_events[0], Mapping) else {}
        detail = _first_nonempty(first.get("summary"), first.get("event_type"), "the failed event")
        return f"Inspect {detail} and its raw replay event before deciding on a repair."
    if lowered in {"finished", "completed", "done", "success"}:
        return "Check the final output and confirm the replay timeline matches the expected task flow."
    if lowered in {"running", "pending", "queued", "in_progress"}:
        latest = _first_nonempty(latest_event.get("summary"), latest_event.get("event_type"), "the latest runtime event")
        return f"Check {latest} and confirm the task is still progressing."
    if lowered in {"failed", "error"}:
        return "Inspect the latest replay event and task error fields before deciding on a repair."
    return "Inspect the replay snapshot fields before deciding the next human action."


def _extract_blockers(snapshot: Mapping[str, Any]) -> List[str]:
    blockers = snapshot.get("blockers")
    if isinstance(blockers, list):
        extracted = [_blocker_text(item) for item in blockers]
        return [item for item in extracted if item]

    task = snapshot.get("raw_task")
    if isinstance(task, Mapping):
        reason = _first_nonempty(task.get("blocked_reason"), task.get("failure_message"), task.get("last_error"), task.get("error"))
        if reason and str(snapshot.get("status") or "").lower() == "blocked":
            return [reason]
    return []


def _blocker_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return _first_nonempty(value.get("reason"), value.get("blocked_reason"), value.get("message"), value.get("error"), value.get("type"))
    return ""


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
