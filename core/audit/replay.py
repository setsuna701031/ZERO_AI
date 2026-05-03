from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.audit.query import query_events_by_task_id


TERMINAL_EVENT_TYPE = "execution_finished_or_failed"
POLICY_EVENT_TYPE = "planned_or_policy"


def replay_task_audit(workspace_root: str, task_id: str) -> Dict[str, Any]:
    resolved_task_id = str(task_id or "").strip()
    if not resolved_task_id:
        return {
            "ok": False,
            "error": "task_id is required",
            "task_id": "",
            "event_count": 0,
        }

    events = query_events_by_task_id(workspace_root, resolved_task_id)
    if not events:
        return {
            "ok": False,
            "error": "audit events not found",
            "task_id": resolved_task_id,
            "event_count": 0,
        }

    return build_replay_summary(events, task_id=resolved_task_id)


def build_replay_summary(events: List[Dict[str, Any]], task_id: str = "") -> Dict[str, Any]:
    clean_events = [event for event in events if isinstance(event, dict)]
    sequence = [str(event.get("event_type") or "unknown") for event in clean_events]
    sources = [
        str(event.get("source") or "unknown")
        for event in clean_events
        if str(event.get("source") or "").strip()
    ]
    unique_sources = sorted(set(sources))

    terminal_events = [
        event for event in clean_events if str(event.get("event_type") or "") == TERMINAL_EVENT_TYPE
    ]
    last_terminal = terminal_events[-1] if terminal_events else {}
    last_policy = _last_nonempty(clean_events, "policy_decision", default="unknown")
    last_execution_status = _last_nonempty(clean_events, "execution_status", default="unknown")
    final_status = str(
        last_terminal.get("status")
        or last_terminal.get("execution_status")
        or _last_nonempty(clean_events, "status", default="unknown")
    ).strip().lower() or "unknown"

    return {
        "ok": True,
        "task_id": task_id or str((clean_events[0] if clean_events else {}).get("task_id") or ""),
        "event_count": len(clean_events),
        "event_sequence": sequence,
        "has_created": "created" in sequence,
        "has_policy_event": POLICY_EVENT_TYPE in sequence,
        "has_terminal_event": bool(terminal_events),
        "final_status": final_status if final_status in {"finished", "failed", "blocked"} else "unknown",
        "policy_decision": last_policy,
        "execution_status": last_execution_status,
        "source_consistent": len(unique_sources) <= 1,
        "source": unique_sources[0] if len(unique_sources) == 1 else "mixed" if unique_sources else "unknown",
        "sources": unique_sources,
        "first_timestamp": str(clean_events[0].get("timestamp") or "") if clean_events else "",
        "last_timestamp": str(clean_events[-1].get("timestamp") or "") if clean_events else "",
        "errors": [
            str(event.get("error") or "")
            for event in clean_events
            if str(event.get("error") or "").strip()
        ],
    }


def compare_audit_event_sequence(
    left_events: List[Dict[str, Any]],
    right_events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    left = build_replay_summary(left_events)
    right = build_replay_summary(right_events)
    return compare_replay_summaries(left, right)


def compare_replay_summaries(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    left_sequence = list(left.get("event_sequence", [])) if isinstance(left.get("event_sequence"), list) else []
    right_sequence = list(right.get("event_sequence", [])) if isinstance(right.get("event_sequence"), list) else []
    return {
        "ok": True,
        "same_sequence": left_sequence == right_sequence,
        "left_task_id": str(left.get("task_id") or ""),
        "right_task_id": str(right.get("task_id") or ""),
        "left_event_sequence": left_sequence,
        "right_event_sequence": right_sequence,
        "missing_in_left": _ordered_difference(right_sequence, left_sequence),
        "missing_in_right": _ordered_difference(left_sequence, right_sequence),
        "same_final_status": str(left.get("final_status") or "") == str(right.get("final_status") or ""),
        "same_policy_decision": str(left.get("policy_decision") or "") == str(right.get("policy_decision") or ""),
        "same_execution_status": str(left.get("execution_status") or "") == str(right.get("execution_status") or ""),
        "source_consistent": bool(left.get("source_consistent")) and bool(right.get("source_consistent")),
    }


def _last_nonempty(events: List[Dict[str, Any]], key: str, default: str = "") -> str:
    for event in reversed(events):
        value = str(event.get(key) or "").strip()
        if value:
            return value
    return default


def _ordered_difference(source: List[str], target: List[str]) -> List[str]:
    remaining = list(target)
    missing: List[str] = []
    for item in source:
        if item in remaining:
            remaining.remove(item)
        else:
            missing.append(item)
    return missing
