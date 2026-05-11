from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Tuple

from core.tasks.runtime_kernel_events import normalize_runtime_kernel_event
from core.tasks.runtime_state_hygiene import clone_runtime_export, freeze_runtime_export


FAILURE_STATUSES = {"failed", "failure", "error", "invalid", "blocked", "rejected"}


def build_runtime_timeline(events: Any) -> List[Dict[str, Any]]:
    if events is None:
        return []
    if not isinstance(events, list):
        events = [events]

    prepared: List[Tuple[int, Optional[float], Dict[str, Any]]] = []
    for original_index, event in enumerate(events):
        normalized = _ensure_normalized_event(event)
        prepared.append((original_index, _parse_timestamp(normalized.get("timestamp")), normalized))

    prepared.sort(
        key=lambda item: (
            1 if item[1] is None else 0,
            item[1] if item[1] is not None else item[0],
            item[0],
        )
    )

    timeline: List[Dict[str, Any]] = []
    for sequence_index, (_original_index, _parsed_ts, event) in enumerate(prepared):
        timeline.append(
            {
                "sequence_index": sequence_index,
                "source": str(event.get("source") or "unknown"),
                "event_type": str(event.get("event_type") or "unknown_event"),
                "status": str(event.get("status") or "unknown"),
                "summary": str(event.get("summary") or ""),
                "timestamp": event.get("timestamp", ""),
                "raw": freeze_runtime_export(event.get("raw")),
            }
        )
    return timeline


def summarize_runtime_timeline(timeline: Any) -> Dict[str, Any]:
    safe_timeline = timeline if isinstance(timeline, list) else build_runtime_timeline(timeline)
    first = get_first_timeline_event(safe_timeline)
    latest = get_latest_timeline_event(safe_timeline)
    failed = get_failed_timeline_events(safe_timeline)

    by_source: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    for item in safe_timeline:
        if not isinstance(item, Mapping):
            continue
        source = str(item.get("source") or "unknown")
        status = str(item.get("status") or "unknown")
        by_source[source] = by_source.get(source, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1

    return {
        "ok": True,
        "event_count": len([item for item in safe_timeline if isinstance(item, Mapping)]),
        "failed_event_count": len(failed),
        "first_event": first,
        "latest_event": latest,
        "by_source": by_source,
        "by_status": by_status,
    }


def get_latest_timeline_event(timeline: Any) -> Dict[str, Any]:
    if not isinstance(timeline, list) or not timeline:
        return {}
    for item in reversed(timeline):
        if isinstance(item, Mapping):
            return dict(item)
    return {}


def get_first_timeline_event(timeline: Any) -> Dict[str, Any]:
    if not isinstance(timeline, list) or not timeline:
        return {}
    for item in timeline:
        if isinstance(item, Mapping):
            return dict(item)
    return {}


def get_failed_timeline_events(timeline: Any) -> List[Dict[str, Any]]:
    if not isinstance(timeline, list):
        return []
    failed: List[Dict[str, Any]] = []
    for item in timeline:
        if not isinstance(item, Mapping):
            continue
        status = str(item.get("status") or "").strip().lower()
        if status in FAILURE_STATUSES:
            failed.append(dict(item))
    return failed


def _ensure_normalized_event(event: Any) -> Dict[str, Any]:
    if isinstance(event, Mapping) and _looks_normalized(event):
        return {
            "source": str(event.get("source") or "unknown"),
            "event_type": str(event.get("event_type") or "unknown_event"),
            "status": str(event.get("status") or "unknown"),
            "summary": str(event.get("summary") or ""),
            "timestamp": event.get("timestamp", ""),
            "raw": clone_runtime_export(event.get("raw")),
        }
    return normalize_runtime_kernel_event(event)


def _looks_normalized(event: Mapping[str, Any]) -> bool:
    required = {"source", "event_type", "status", "summary", "timestamp", "raw"}
    return required.issubset(set(event.keys()))


def _parse_timestamp(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        pass

    normalized = text
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except Exception:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()
