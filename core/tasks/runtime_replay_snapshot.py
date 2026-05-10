from __future__ import annotations

from typing import Any, Dict, List, Mapping

from core.tasks.runtime_kernel_events import normalize_runtime_kernel_events
from core.tasks.runtime_kernel_status import build_runtime_kernel_status_from_events
from core.tasks.runtime_kernel_timeline import (
    build_runtime_timeline,
    get_failed_timeline_events,
    get_latest_timeline_event,
    summarize_runtime_timeline,
)
from core.tasks.runtime_state_hygiene import freeze_runtime_export, safe_deepcopy


def build_runtime_replay_snapshot(task: Any) -> Dict[str, Any]:
    raw_task = freeze_runtime_export(task)
    safe_task = task if isinstance(task, Mapping) else {}

    planner_events = _collect_trace_events(
        safe_task,
        ("planner_trace", "planner_events", "planner_contract_trace", "plan_trace"),
    )
    execution_events = _collect_trace_events(
        safe_task,
        ("execution_trace", "execution_log", "execution_events", "step_results", "results"),
    )
    blocker_events = _collect_blocker_events(safe_task)
    repair_events = _collect_trace_events(
        safe_task,
        ("repair_trace", "repair_events", "repair_log"),
    ) + _collect_repair_context_events(safe_task.get("repair_context"))
    runtime_events = _collect_trace_events(
        safe_task,
        ("runtime_trace", "runtime_events", "runtime_log"),
    )

    normalized_events = (
        normalize_runtime_kernel_events(planner_events, source="planner")
        + normalize_runtime_kernel_events(execution_events, source="execution")
        + normalize_runtime_kernel_events(blocker_events, source="blocker")
        + normalize_runtime_kernel_events(repair_events, source="repair")
        + normalize_runtime_kernel_events(runtime_events, source="runtime")
    )
    timeline = build_runtime_timeline(normalized_events)
    timeline_summary = summarize_runtime_timeline(timeline)
    latest_event = get_latest_timeline_event(timeline)
    failed_events = get_failed_timeline_events(timeline)
    blockers = _extract_blockers(safe_task)
    kernel_status = build_runtime_kernel_status_from_events(
        planner_events=planner_events,
        execution_events=execution_events,
    )

    status = _first_nonempty(safe_task.get("status"), "unknown")
    task_id = _first_nonempty(safe_task.get("task_id"), safe_task.get("task_name"), safe_task.get("id"), safe_task.get("name"))
    goal = _first_nonempty(safe_task.get("goal"), safe_task.get("title"), safe_task.get("prompt"), safe_task.get("query"), safe_task.get("input"))

    return {
        "task_id": task_id,
        "status": status,
        "goal": goal,
        "kernel_status": kernel_status,
        "normalized_events": normalized_events,
        "timeline": timeline,
        "timeline_summary": timeline_summary,
        "latest_event": latest_event,
        "failed_events": failed_events,
        "blockers": blockers,
        "replay_summary": _build_replay_summary(
            task_id=task_id,
            status=status,
            goal=goal,
            timeline_summary=timeline_summary,
            latest_event=latest_event,
            failed_events=failed_events,
            blockers=blockers,
        ),
        "raw_task": raw_task,
    }


def _collect_trace_events(task: Mapping[str, Any], keys: tuple[str, ...]) -> List[Any]:
    events: List[Any] = []
    for key in keys:
        value = task.get(key)
        if isinstance(value, list):
            events.extend(safe_deepcopy(value))
        elif isinstance(value, Mapping):
            events.append(safe_deepcopy(value))
    return events


def _collect_blocker_events(task: Mapping[str, Any]) -> List[Any]:
    events: List[Any] = []
    for blocker in _extract_blockers(task):
        events.append({"event": "task_blocked", "blocked_reason": blocker})
    return events


def _collect_repair_context_events(value: Any) -> List[Any]:
    if not isinstance(value, Mapping):
        return []

    events: List[Any] = []
    for key in ("events", "trace", "history", "strategy_history", "injections"):
        item = value.get(key)
        if isinstance(item, list):
            events.extend(safe_deepcopy(item))
        elif isinstance(item, Mapping):
            events.append(safe_deepcopy(item))

    summary = _first_nonempty(value.get("summary"), value.get("reason"), value.get("classification"))
    if summary:
        events.append({"event": "repair_context", "repair_action": summary})
    return events


def _extract_blockers(task: Mapping[str, Any]) -> List[str]:
    blockers: List[str] = []
    for key in ("unresolved_blockers", "active_blockers", "blockers"):
        value = task.get(key)
        if isinstance(value, list):
            for item in value:
                text = _blocker_text(item)
                if text:
                    blockers.append(text)
        else:
            text = _blocker_text(value)
            if text:
                blockers.append(text)

    if str(task.get("status") or "").strip().lower() == "blocked":
        reason = _first_nonempty(
            task.get("blocked_reason"),
            task.get("failure_message"),
            task.get("last_error"),
            task.get("error"),
        )
        if reason:
            blockers.append(reason)

    seen = set()
    unique: List[str] = []
    for blocker in blockers:
        if blocker in seen:
            continue
        seen.add(blocker)
        unique.append(blocker)
    return unique


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


def _build_replay_summary(
    *,
    task_id: str,
    status: str,
    goal: str,
    timeline_summary: Mapping[str, Any],
    latest_event: Mapping[str, Any],
    failed_events: List[Dict[str, Any]],
    blockers: List[str],
) -> str:
    subject = task_id or goal or "task"
    event_count = int(timeline_summary.get("event_count", 0) or 0)
    latest = str(latest_event.get("summary") or "no latest event").strip()
    parts = [f"{subject} is {status or 'unknown'} with {event_count} replay event(s)."]
    if failed_events:
        parts.append(f"{len(failed_events)} event(s) need attention.")
    if blockers:
        parts.append(f"Blocker: {blockers[0]}.")
    parts.append(f"Latest: {latest}.")
    return " ".join(parts)


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
