from __future__ import annotations

import copy
from typing import Any, Dict, List, Mapping, Optional


KERNEL_EVENT_SOURCES = {"planner", "execution", "blocker", "repair", "runtime", "unknown"}


def normalize_runtime_kernel_event(event: Any, *, source: Optional[str] = None) -> Dict[str, Any]:
    raw = copy.deepcopy(event)
    is_malformed = not isinstance(event, Mapping)
    payload = event if isinstance(event, Mapping) else {}
    resolved_source = _normalize_source(source) or _infer_source(payload)
    event_type = _event_type(payload)
    status = _event_status(payload, resolved_source)

    return {
        "source": resolved_source,
        "event_type": event_type,
        "status": status,
        "summary": "malformed event" if is_malformed else _event_summary(payload, resolved_source, event_type),
        "timestamp": _event_timestamp(payload),
        "raw": raw,
    }


def normalize_runtime_kernel_events(trace: Any, *, source: Optional[str] = None) -> List[Dict[str, Any]]:
    if trace is None:
        return []
    if isinstance(trace, list):
        return [normalize_runtime_kernel_event(item, source=source) for item in trace]
    if isinstance(trace, Mapping):
        return [normalize_runtime_kernel_event(trace, source=source)]
    return [normalize_runtime_kernel_event(trace, source=source)]


def summarize_normalized_kernel_events(events: Any) -> Dict[str, Any]:
    normalized = normalize_runtime_kernel_events(events)
    by_source = {source: 0 for source in sorted(KERNEL_EVENT_SOURCES)}
    by_status: Dict[str, int] = {}
    latest_event: Dict[str, Any] = {}

    for event in normalized:
        source = str(event.get("source") or "unknown")
        status = str(event.get("status") or "unknown")
        by_source[source] = by_source.get(source, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
        latest_event = event

    return {
        "ok": True,
        "event_count": len(normalized),
        "by_source": by_source,
        "by_status": by_status,
        "latest_event": latest_event,
    }


def _normalize_source(source: Optional[str]) -> str:
    text = str(source or "").strip().lower()
    if text in KERNEL_EVENT_SOURCES:
        return text
    return ""


def _infer_source(payload: Mapping[str, Any]) -> str:
    if not isinstance(payload, Mapping):
        return "unknown"

    explicit = _normalize_source(str(payload.get("source") or ""))
    if explicit:
        return explicit

    lowered_event = " ".join(
        str(payload.get(key) or "").lower()
        for key in ("event", "event_type", "action", "type", "reason", "blocked_reason")
    )
    keys = {str(key).lower() for key in payload.keys()}

    if "blocked_reason" in keys or "blocker" in lowered_event or "blocked" in lowered_event:
        return "blocker"
    if "repair" in lowered_event or any(key.startswith("repair") for key in keys):
        return "repair"
    if "current_step_index" in keys or "runtime_state" in keys or "runtime" in lowered_event:
        return "runtime"
    if "planner_gateway_ok" in keys or "raw_action" in keys or "intent" in keys or "plan" in keys:
        return "planner"
    if "execution_runtime_entry_ok" in keys or "result_ok" in keys or "result_error" in keys:
        return "execution"
    if "step" in keys or "result" in keys or "command" in keys:
        return "execution"
    return "unknown"


def _event_type(payload: Mapping[str, Any]) -> str:
    return _first_nonempty(
        payload.get("event"),
        payload.get("event_type"),
        payload.get("action"),
        payload.get("type"),
        "unknown_event",
    )


def _event_status(payload: Mapping[str, Any], source: str) -> str:
    status = _first_nonempty(payload.get("status"))
    if status:
        return status

    result = payload.get("result")
    if isinstance(result, Mapping):
        nested_status = _first_nonempty(result.get("status"))
        if nested_status:
            return nested_status
        if "ok" in result:
            return "ok" if bool(result.get("ok")) else "error"

    if "ok" in payload:
        return "ok" if bool(payload.get("ok")) else "error"
    if "is_valid" in payload:
        return "ok" if bool(payload.get("is_valid")) else "invalid"
    if "result_ok" in payload and payload.get("result_ok") is not None:
        return "ok" if bool(payload.get("result_ok")) else "error"
    if _first_nonempty(payload.get("error"), payload.get("result_error")):
        return "error"
    if source == "blocker":
        return "blocked"
    return "unknown"


def _event_timestamp(payload: Mapping[str, Any]) -> Any:
    return payload.get("timestamp", payload.get("ts", payload.get("time", payload.get("created_at", ""))))


def _event_summary(payload: Mapping[str, Any], source: str, event_type: str) -> str:
    if not isinstance(payload, Mapping):
        return "malformed event"
    if source == "blocker":
        reason = _first_nonempty(payload.get("reason"), payload.get("blocked_reason"), payload.get("message"), payload.get("error"))
        return f"blocker: {reason or event_type}"
    if source == "execution":
        action = _first_nonempty(payload.get("action"), payload.get("type"), payload.get("tool"), event_type)
        result = payload.get("result")
        result_text = ""
        if isinstance(result, Mapping):
            result_text = _first_nonempty(result.get("status"), result.get("action"), result.get("message"))
            error = _first_nonempty(result.get("error"))
        else:
            error = ""
        error = error or _first_nonempty(payload.get("result_error"), payload.get("error"), payload.get("reason"))
        if error:
            return f"execution action: {action}; error: {error}"
        if result_text:
            return f"execution action: {action}; result: {result_text}"
        return f"execution action: {action}"
    if source == "planner":
        intent = _first_nonempty(payload.get("intent"), payload.get("action"), payload.get("raw_action"))
        plan = _extract_plan_text(payload.get("plan"))
        step = _extract_step_text(payload.get("step"))
        detail = _first_nonempty(plan, step, intent, event_type)
        return f"planner: {detail}"
    if source == "repair":
        detail = _first_nonempty(payload.get("repair_action"), payload.get("action"), payload.get("reason"), payload.get("error"), event_type)
        return f"repair: {detail}"
    if source == "runtime":
        detail = _first_nonempty(_extract_step_text(payload.get("step")), payload.get("current_step"), payload.get("status"), event_type)
        return f"runtime: {detail}"
    return _first_nonempty(payload.get("summary"), payload.get("message"), payload.get("reason"), event_type)


def _extract_plan_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return _first_nonempty(value.get("title"), value.get("goal"), value.get("intent"), value.get("action"), value.get("summary"))
    if isinstance(value, list) and value:
        return _extract_step_text(value[0])
    return ""


def _extract_step_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        nested = _extract_step_text(value.get("step"))
        if nested:
            return nested
        return _first_nonempty(value.get("title"), value.get("name"), value.get("description"), value.get("action"), value.get("type"))
    return ""


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
