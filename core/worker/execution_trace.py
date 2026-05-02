from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


TRACE_SCHEMA_VERSION = "worker_trace_v1"
TRACE_COMPONENTS = {"worker", "scheduler", "aggregation"}


@dataclass(frozen=True)
class TraceEvent:
    event_id: str
    component: str
    event_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = TRACE_SCHEMA_VERSION
    sequence: int = 0
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "sequence": self.sequence,
            "ts": self.ts,
            "component": self.component,
            "event_type": self.event_type,
            "payload": copy.deepcopy(self.payload),
        }


class TraceRecorder:
    def __init__(self) -> None:
        self._events: List[Dict[str, Any]] = []

    def record(
        self,
        *,
        component: str,
        event_type: str,
        payload: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        event = create_trace_event(
            component=component,
            event_type=event_type,
            payload=payload or {},
            sequence=len(self._events) + 1,
        )
        event_payload = event.to_dict()
        self._events.append(copy.deepcopy(event_payload))
        return event_payload

    def events(self) -> List[Dict[str, Any]]:
        return [copy.deepcopy(event) for event in self._events]


def create_trace_event(
    *,
    component: str,
    event_type: str,
    payload: Dict[str, Any],
    sequence: int,
    ts: str | None = None,
) -> TraceEvent:
    normalized_component = str(component or "").strip().lower()
    if normalized_component not in TRACE_COMPONENTS:
        raise ValueError(f"trace component must be one of {sorted(TRACE_COMPONENTS)}")

    normalized_type = str(event_type or "").strip()
    if not normalized_type:
        raise ValueError("trace event_type is required")

    safe_payload = _json_safe(payload if isinstance(payload, dict) else {})
    event_id = _stable_event_id(
        sequence=sequence,
        component=normalized_component,
        event_type=normalized_type,
        payload=safe_payload,
    )
    return TraceEvent(
        event_id=event_id,
        sequence=max(0, int(sequence or 0)),
        ts=ts or datetime.now(timezone.utc).isoformat(),
        component=normalized_component,
        event_type=normalized_type,
        payload=safe_payload,
    )


def ensure_trace_event_contract(event: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(event, dict):
        raise ValueError("trace_event must be a dict")

    required = {"schema_version", "event_id", "sequence", "ts", "component", "event_type", "payload"}
    missing = sorted(key for key in required if key not in event)
    if missing:
        raise ValueError(f"trace_event missing fields: {missing}")

    if event.get("schema_version") != TRACE_SCHEMA_VERSION:
        raise ValueError(f"unsupported trace schema: {event.get('schema_version')}")
    if str(event.get("component") or "") not in TRACE_COMPONENTS:
        raise ValueError(f"invalid trace component: {event.get('component')}")
    if not str(event.get("event_type") or "").strip():
        raise ValueError("trace_event.event_type is required")
    if not isinstance(event.get("payload"), dict):
        raise ValueError("trace_event.payload must be a dict")

    try:
        sequence = int(event.get("sequence"))
    except Exception as exc:
        raise ValueError(f"trace_event.sequence must be an integer: {exc}") from exc
    if sequence < 0:
        raise ValueError("trace_event.sequence must be >= 0")

    return copy.deepcopy(event)


def trace_digest(events: List[Dict[str, Any]]) -> str:
    normalized = []
    for event in events:
        checked = ensure_trace_event_contract(event)
        stable = {
            "schema_version": checked["schema_version"],
            "sequence": checked["sequence"],
            "component": checked["component"],
            "event_type": checked["event_type"],
            "payload": checked["payload"],
        }
        normalized.append(stable)
    text = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TraceReplayRuntime:
    def replay(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        checked_events = [ensure_trace_event_contract(event) for event in events]
        checked_events.sort(key=lambda event: int(event.get("sequence") or 0))

        scheduler_state = {
            "queue": [],
            "done": [],
            "failed": [],
            "tick_count": 0,
            "last_event": "",
        }
        worker_results: List[Dict[str, Any]] = []
        final_result: Dict[str, Any] = {}

        for event in checked_events:
            component = event["component"]
            event_type = event["event_type"]
            payload = copy.deepcopy(event["payload"])

            if component == "scheduler":
                self._apply_scheduler_event(scheduler_state, event_type, payload)
            elif component == "worker" and event_type == "worker_result":
                result = payload.get("worker_result")
                if isinstance(result, dict):
                    worker_results.append(copy.deepcopy(result))
            elif component == "aggregation" and event_type == "final_result":
                result = payload.get("final_result")
                if isinstance(result, dict):
                    final_result = copy.deepcopy(result)

        return {
            "ok": True,
            "event_count": len(checked_events),
            "trace_digest": trace_digest(checked_events),
            "scheduler_state": scheduler_state,
            "worker_results": worker_results,
            "final_result": final_result,
        }

    def _apply_scheduler_event(
        self,
        scheduler_state: Dict[str, Any],
        event_type: str,
        payload: Dict[str, Any],
    ) -> None:
        if event_type == "enqueue":
            item = payload.get("queue_item")
            if isinstance(item, dict):
                scheduler_state["queue"].append(copy.deepcopy(item))
                scheduler_state["last_event"] = f"enqueued:{_task_id_from_item(item)}"
            return

        if event_type == "tick":
            scheduler_state["tick_count"] += 1
            scheduler_state["last_event"] = "tick"
            return

        if event_type in {"done", "failed", "retry"}:
            task_id = str(payload.get("task_id") or "").strip()
            item = self._pop_queue_item(scheduler_state["queue"], task_id)
            if not item:
                item = payload.get("queue_item") if isinstance(payload.get("queue_item"), dict) else {}
            if item:
                item = copy.deepcopy(item)
                if event_type == "retry":
                    item["status"] = "pending"
                    scheduler_state["queue"].append(item)
                elif event_type == "done":
                    item["status"] = "done"
                    scheduler_state["done"].append(item)
                else:
                    item["status"] = "failed"
                    scheduler_state["failed"].append(item)
            scheduler_state["last_event"] = f"{event_type}:{task_id}"

    def _pop_queue_item(self, queue: List[Dict[str, Any]], task_id: str) -> Dict[str, Any]:
        for index, item in enumerate(queue):
            if _task_id_from_item(item) == task_id:
                return queue.pop(index)
        return {}


def _task_id_from_item(item: Dict[str, Any]) -> str:
    task = item.get("task") if isinstance(item.get("task"), dict) else {}
    return str(task.get("task_id") or "").strip()


def _stable_event_id(
    *,
    sequence: int,
    component: str,
    event_type: str,
    payload: Dict[str, Any],
) -> str:
    body = {
        "sequence": sequence,
        "component": component,
        "event_type": event_type,
        "payload": payload,
    }
    text = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)
