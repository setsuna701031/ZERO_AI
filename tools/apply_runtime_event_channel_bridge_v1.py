from __future__ import annotations

from pathlib import Path


EVENT_STREAM_PATH = Path("core/runtime/event_stream.py")
TEST_PATH = Path("tests/test_runtime_event_channel_bridge_contract.py")


EVENT_STREAM_CONTENT = r'''from __future__ import annotations

import copy
from typing import Any, Dict, List

from core.runtime.event_normalizer import (
    normalize_runtime_event_envelope,
    normalize_runtime_event_stream_envelope,
)


def normalize_runtime_event(event: Any, *, source: str = "") -> Dict[str, Any]:
    return normalize_runtime_event_envelope(event, source=source)


def runtime_event_stream_from_trace(trace: Any, *, source: str = "execution_trace") -> List[Dict[str, Any]]:
    if hasattr(trace, "to_dict") and callable(getattr(trace, "to_dict")):
        payload = trace.to_dict()
    elif isinstance(trace, dict):
        payload = trace
    elif isinstance(trace, list):
        payload = {"events": trace}
    else:
        payload = {"events": []}

    return normalize_runtime_event_stream_envelope(payload, source=source)


def runtime_event_stream_from_adapter_payload(payload: Any, *, source: str = "adapter_payload") -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    adapter = payload.get("adapter_payload")
    if isinstance(adapter, dict):
        trace = adapter.get("execution_trace")
        if isinstance(trace, list):
            return normalize_runtime_event_stream_envelope(trace, source=source)

        event = adapter.get("observability_event")
        if isinstance(event, dict):
            return normalize_runtime_event_stream_envelope([event], source=source)

    trace = payload.get("execution_trace")
    if isinstance(trace, list):
        return normalize_runtime_event_stream_envelope(trace, source=source)

    event = payload.get("observability_event")
    if isinstance(event, dict):
        return normalize_runtime_event_stream_envelope([event], source=source)

    return []


def attach_runtime_event_stream(payload: Any, *, source: str = "runtime") -> Any:
    if not isinstance(payload, dict):
        return payload

    if isinstance(payload.get("runtime_event_stream"), list):
        payload["runtime_event_stream"] = normalize_runtime_event_stream_envelope(
            payload.get("runtime_event_stream"),
            source=source,
        )
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

        merged.extend(normalize_runtime_event_stream_envelope(stream, source="runtime"))

    return sorted(merged, key=lambda item: float(item.get("timestamp") or 0))


class RuntimeEventChannel:
    """
    Append-only in-memory runtime event channel.

    Schema ownership belongs to core.runtime.event_normalizer.
    This channel only handles append / snapshot / cursor transport.
    """

    def __init__(self) -> None:
        self._events: List[Dict[str, Any]] = []
        self._cursor: int = 0

    def append_event(self, event: Any, *, source: str = "runtime") -> Dict[str, Any]:
        normalized = normalize_runtime_event_envelope(event, source=source)
        self._cursor += 1
        normalized["cursor"] = self._cursor
        self._events.append(copy.deepcopy(normalized))
        return copy.deepcopy(normalized)

    def append_events(self, events: Any, *, source: str = "runtime") -> List[Dict[str, Any]]:
        if isinstance(events, dict):
            if isinstance(events.get("runtime_event_stream"), list):
                events = events.get("runtime_event_stream")
            elif isinstance(events.get("events"), list):
                events = runtime_event_stream_from_trace(events, source=source)
            else:
                events = runtime_event_stream_from_adapter_payload(events, source=source)

        if not isinstance(events, list):
            return []

        appended: List[Dict[str, Any]] = []
        for event in events:
            if isinstance(event, dict):
                appended.append(self.append_event(event, source=source))
        return appended

    def snapshot(self, *, limit: int | None = None) -> Dict[str, Any]:
        events = copy.deepcopy(self._events)
        if isinstance(limit, int) and limit >= 0:
            events = events[-limit:]

        return {
            "ok": True,
            "runtime_phase": "event_channel",
            "cursor": self._cursor,
            "event_count": len(self._events),
            "events": events,
        }

    def events_since(self, cursor: int = 0, *, limit: int | None = None) -> Dict[str, Any]:
        try:
            cursor_value = int(cursor)
        except Exception:
            cursor_value = 0

        events = [event for event in self._events if int(event.get("cursor", 0) or 0) > cursor_value]
        if isinstance(limit, int) and limit >= 0:
            events = events[:limit]

        return {
            "ok": True,
            "runtime_phase": "event_channel",
            "cursor": self._cursor,
            "from_cursor": cursor_value,
            "event_count": len(events),
            "events": copy.deepcopy(events),
        }

    def latest_cursor(self) -> int:
        return int(self._cursor)

    def clear(self) -> None:
        self._events = []
        self._cursor = 0
'''


TEST_CONTENT = r'''from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeEventChannelBridgeContractTest(unittest.TestCase):
    def test_runtime_event_stream_uses_envelope_schema(self) -> None:
        from core.runtime.event_stream import runtime_event_stream_from_adapter_payload

        payload: Dict[str, Any] = {
            "adapter_payload": {
                "execution_trace": [
                    {
                        "event_type": "step",
                        "runtime_mode": "execute",
                        "task_id": "task-1",
                        "ok": True,
                        "status": "done",
                    }
                ]
            }
        }

        stream = runtime_event_stream_from_adapter_payload(payload, source="adapter")

        self.assertEqual(len(stream), 1)
        self.assertEqual(stream[0]["event_type"], "step")
        self.assertEqual(stream[0]["runtime_phase"], "execute")
        self.assertEqual(stream[0]["task_id"], "task-1")
        self.assertEqual(stream[0]["source"], "adapter")
        self.assertEqual(stream[0]["payload"]["status"], "done")
        self.assertIn("timestamp", stream[0])

    def test_runtime_event_channel_stores_envelope_schema(self) -> None:
        from core.runtime.event_stream import RuntimeEventChannel

        channel = RuntimeEventChannel()
        event = channel.append_event(
            {
                "event_type": "execution_guard",
                "runtime_mode": "guard",
                "task_id": "task-2",
                "ok": False,
                "error_text": "blocked",
            },
            source="guard",
        )

        self.assertEqual(event["cursor"], 1)
        self.assertEqual(event["event_type"], "execution_guard")
        self.assertEqual(event["runtime_phase"], "guard")
        self.assertEqual(event["task_id"], "task-2")
        self.assertEqual(event["payload"]["error_text"], "blocked")
        self.assertEqual(channel.snapshot()["events"][0]["runtime_phase"], "guard")

    def test_merge_runtime_event_streams_sorts_by_timestamp_envelope(self) -> None:
        from core.runtime.event_stream import merge_runtime_event_streams

        stream = merge_runtime_event_streams(
            [{"timestamp": 3, "event_type": "third"}],
            [{"timestamp": 1, "event_type": "first"}],
            [{"timestamp": 2, "event_type": "second"}],
        )

        self.assertEqual([item["event_type"] for item in stream], ["first", "second", "third"])

    def test_attach_runtime_event_stream_normalizes_existing_stream(self) -> None:
        from core.runtime.event_stream import attach_runtime_event_stream

        payload: Dict[str, Any] = {
            "runtime_event_stream": [
                {
                    "event_type": "status",
                    "runtime_mode": "execute",
                    "task_id": "task-3",
                    "status": "running",
                }
            ]
        }

        adapted = attach_runtime_event_stream(payload, source="existing")
        stream = adapted.get("runtime_event_stream")

        self.assertEqual(len(stream), 1)
        self.assertEqual(stream[0]["runtime_phase"], "execute")
        self.assertEqual(stream[0]["payload"]["status"], "running")
        self.assertEqual(stream[0]["source"], "existing")


if __name__ == "__main__":
    unittest.main()
'''


def main() -> None:
    EVENT_STREAM_PATH.write_text(EVENT_STREAM_CONTENT, encoding="utf-8")
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")

    print("[runtime-event-channel-bridge-v1] updated core/runtime/event_stream.py")
    print("[runtime-event-channel-bridge-v1] created tests/test_runtime_event_channel_bridge_contract.py")


if __name__ == "__main__":
    main()