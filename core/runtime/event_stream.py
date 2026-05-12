from __future__ import annotations

import copy
import time
from typing import Any, Dict, List


def normalize_runtime_event(event: Any, *, source: str = "") -> Dict[str, Any]:
    if not isinstance(event, dict):
        return {
            "ts": time.time(),
            "event_type": "unknown",
            "source": str(source or "runtime"),
            "ok": True,
            "runtime_mode": "event_stream",
            "data": {},
            "raw": event,
        }

    raw = copy.deepcopy(event)

    event_type = str(
        event.get("event_type")
        or event.get("type")
        or event.get("name")
        or "runtime_event"
    ).strip()

    data = event.get("data")
    if not isinstance(data, dict):
        data = {
            key: copy.deepcopy(value)
            for key, value in event.items()
            if key not in {"ts", "event_type", "type", "name", "source", "raw"}
        }

    ok = event.get("ok")
    if ok is None and isinstance(data, dict) and "ok" in data:
        ok = data.get("ok")
    if ok is None:
        ok = True

    runtime_mode = str(
        event.get("runtime_mode")
        or data.get("runtime_mode")
        or "event_stream"
    ).strip()

    return {
        "ts": event.get("ts") or time.time(),
        "event_type": event_type or "runtime_event",
        "source": str(source or event.get("source") or "runtime"),
        "ok": bool(ok),
        "runtime_mode": runtime_mode or "event_stream",
        "task_id": str(event.get("task_id") or data.get("task_id") or ""),
        "status": str(event.get("status") or data.get("status") or ""),
        "error_text": str(event.get("error_text") or data.get("error_text") or data.get("error") or ""),
        "data": copy.deepcopy(data),
        "raw": raw,
    }


def runtime_event_stream_from_trace(trace: Any, *, source: str = "execution_trace") -> List[Dict[str, Any]]:
    if hasattr(trace, "to_dict") and callable(getattr(trace, "to_dict")):
        payload = trace.to_dict()
    elif isinstance(trace, dict):
        payload = trace
    elif isinstance(trace, list):
        payload = {"events": trace}
    else:
        payload = {"events": []}

    events = payload.get("events")
    if not isinstance(events, list):
        events = []

    return [normalize_runtime_event(event, source=source) for event in events if isinstance(event, dict)]


def runtime_event_stream_from_adapter_payload(payload: Any, *, source: str = "adapter_payload") -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    adapter = payload.get("adapter_payload")
    if isinstance(adapter, dict):
        trace = adapter.get("execution_trace")
        if isinstance(trace, list):
            return [normalize_runtime_event(event, source=source) for event in trace if isinstance(event, dict)]

        event = adapter.get("observability_event")
        if isinstance(event, dict):
            return [normalize_runtime_event(event, source=source)]

    trace = payload.get("execution_trace")
    if isinstance(trace, list):
        return [normalize_runtime_event(event, source=source) for event in trace if isinstance(event, dict)]

    event = payload.get("observability_event")
    if isinstance(event, dict):
        return [normalize_runtime_event(event, source=source)]

    return []


def attach_runtime_event_stream(payload: Any, *, source: str = "runtime") -> Any:
    if not isinstance(payload, dict):
        return payload

    if isinstance(payload.get("runtime_event_stream"), list):
        return payload

    stream = runtime_event_stream_from_adapter_payload(payload, source=source)

    if not stream and isinstance(payload.get("events"), list):
        stream = runtime_event_stream_from_trace(payload, source=source)

    payload["runtime_event_stream"] = stream
    return payload


def merge_runtime_event_streams(*streams: Any) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []

    for stream in streams:
        if isinstance(stream, dict):
            if isinstance(stream.get("runtime_event_stream"), list):
                stream = stream.get("runtime_event_stream")
            elif isinstance(stream.get("events"), list):
                stream = runtime_event_stream_from_trace(stream)
            else:
                stream = runtime_event_stream_from_adapter_payload(stream)

        if not isinstance(stream, list):
            continue

        for event in stream:
            if isinstance(event, dict):
                merged.append(normalize_runtime_event(event, source=str(event.get("source") or "runtime")))

    return sorted(merged, key=lambda item: float(item.get("ts") or 0))
