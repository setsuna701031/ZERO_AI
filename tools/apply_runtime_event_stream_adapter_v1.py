from __future__ import annotations

from pathlib import Path


EVENT_STREAM_PATH = Path("core/runtime/event_stream.py")
TEST_PATH = Path("tests/test_runtime_event_stream_adapter_contract.py")


EVENT_STREAM_CONTENT = r'''from __future__ import annotations

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
'''


TEST_CONTENT = r'''from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeEventStreamAdapterContractTest(unittest.TestCase):
    def test_event_stream_from_execution_trace(self) -> None:
        from core.runtime.event_stream import runtime_event_stream_from_trace
        from core.tools.execution_trace import ExecutionTrace

        trace = ExecutionTrace()
        trace.add_status_event(
            task_id="task-1",
            status="running",
            tick=1,
            final_answer="",
            extra={"ok": True},
        )

        stream = runtime_event_stream_from_trace(trace)

        self.assertEqual(len(stream), 1)
        self.assertEqual(stream[0]["event_type"], "status")
        self.assertEqual(stream[0]["task_id"], "task-1")
        self.assertEqual(stream[0]["status"], "running")
        self.assertIs(stream[0]["ok"], True)
        self.assertEqual(stream[0]["runtime_mode"], "event_stream")

    def test_event_stream_from_observability_event(self) -> None:
        from core.runtime.event_stream import runtime_event_stream_from_adapter_payload

        payload: Dict[str, Any] = {
            "observability_event": {
                "event_type": "execution_guard",
                "ok": False,
                "runtime_mode": "guard",
                "error_text": "blocked path",
            }
        }

        stream = runtime_event_stream_from_adapter_payload(payload)

        self.assertEqual(len(stream), 1)
        self.assertEqual(stream[0]["event_type"], "execution_guard")
        self.assertIs(stream[0]["ok"], False)
        self.assertEqual(stream[0]["runtime_mode"], "guard")
        self.assertEqual(stream[0]["error_text"], "blocked path")

    def test_attach_runtime_event_stream_from_adapter_payload_trace(self) -> None:
        from core.runtime.event_stream import attach_runtime_event_stream

        payload: Dict[str, Any] = {
            "adapter_payload": {
                "ok": True,
                "runtime_mode": "execute",
                "execution_trace": [
                    {
                        "event_type": "step",
                        "task_id": "task-2",
                        "ok": True,
                        "runtime_mode": "execute",
                    }
                ],
            }
        }

        adapted = attach_runtime_event_stream(payload, source="adapter_payload")
        stream = adapted.get("runtime_event_stream")

        self.assertIsInstance(stream, list)
        self.assertEqual(len(stream), 1)
        self.assertEqual(stream[0]["event_type"], "step")
        self.assertEqual(stream[0]["task_id"], "task-2")
        self.assertEqual(stream[0]["runtime_mode"], "execute")

    def test_merge_runtime_event_streams_sorts_by_timestamp(self) -> None:
        from core.runtime.event_stream import merge_runtime_event_streams

        stream = merge_runtime_event_streams(
            [{"ts": 3, "event_type": "third"}],
            [{"ts": 1, "event_type": "first"}],
            [{"ts": 2, "event_type": "second"}],
        )

        self.assertEqual([item["event_type"] for item in stream], ["first", "second", "third"])


if __name__ == "__main__":
    unittest.main()
'''


def main() -> None:
    EVENT_STREAM_PATH.write_text(EVENT_STREAM_CONTENT, encoding="utf-8")
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")

    print("[runtime-event-stream-adapter-v1] created core/runtime/event_stream.py")
    print("[runtime-event-stream-adapter-v1] created tests/test_runtime_event_stream_adapter_contract.py")


if __name__ == "__main__":
    main()