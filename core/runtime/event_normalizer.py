from __future__ import annotations

import copy
import time
from typing import Any, Dict


def normalize_runtime_event_envelope(event: Any, *, source: str = "") -> Dict[str, Any]:
    raw = copy.deepcopy(event)

    if not isinstance(event, dict):
        return {
            "event_type": "unknown",
            "runtime_phase": "unknown",
            "task_id": "",
            "scheduler_build": "",
            "timestamp": time.time(),
            "source": str(source or "runtime"),
            "ok": True,
            "payload": {"raw": raw},
            "raw": raw,
        }

    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}

    event_type = str(
        event.get("event_type")
        or event.get("type")
        or event.get("name")
        or data.get("event_type")
        or payload.get("event_type")
        or "runtime_event"
    ).strip()

    runtime_phase = str(
        event.get("runtime_phase")
        or event.get("runtime_mode")
        or event.get("phase")
        or data.get("runtime_phase")
        or data.get("runtime_mode")
        or payload.get("runtime_phase")
        or payload.get("runtime_mode")
        or "runtime"
    ).strip()

    task_id = str(
        event.get("task_id")
        or data.get("task_id")
        or payload.get("task_id")
        or ""
    ).strip()

    scheduler_build = str(
        event.get("scheduler_build")
        or data.get("scheduler_build")
        or payload.get("scheduler_build")
        or ""
    ).strip()

    timestamp = event.get("timestamp", event.get("ts", None))
    if timestamp is None:
        timestamp = time.time()

    ok = event.get("ok")
    if ok is None and "ok" in data:
        ok = data.get("ok")
    if ok is None and "ok" in payload:
        ok = payload.get("ok")
    if ok is None:
        ok = True

    normalized_payload: Dict[str, Any] = {}

    if data:
        normalized_payload.update(copy.deepcopy(data))
    if payload:
        normalized_payload.update(copy.deepcopy(payload))

    for key, value in event.items():
        if key in {
            "event_type",
            "type",
            "name",
            "runtime_phase",
            "runtime_mode",
            "phase",
            "task_id",
            "scheduler_build",
            "timestamp",
            "ts",
            "source",
            "ok",
            "payload",
            "data",
            "raw",
        }:
            continue
        normalized_payload[key] = copy.deepcopy(value)

    return {
        "event_type": event_type or "runtime_event",
        "runtime_phase": runtime_phase or "runtime",
        "task_id": task_id,
        "scheduler_build": scheduler_build,
        "timestamp": timestamp,
        "source": str(source or event.get("source") or "runtime"),
        "ok": bool(ok),
        "payload": normalized_payload,
        "raw": raw,
    }


def normalize_runtime_event_stream_envelope(stream: Any, *, source: str = "") -> list[Dict[str, Any]]:
    if isinstance(stream, dict):
        if isinstance(stream.get("runtime_event_stream"), list):
            stream = stream.get("runtime_event_stream")
        elif isinstance(stream.get("events"), list):
            stream = stream.get("events")
        else:
            stream = [stream]

    if not isinstance(stream, list):
        return []

    return [
        normalize_runtime_event_envelope(event, source=source)
        for event in stream
        if isinstance(event, dict)
    ]
