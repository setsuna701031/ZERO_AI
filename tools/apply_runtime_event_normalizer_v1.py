from __future__ import annotations

from pathlib import Path


NORMALIZER_PATH = Path("core/runtime/event_normalizer.py")
EVENT_STREAM_PATH = Path("core/runtime/event_stream.py")
TEST_PATH = Path("tests/test_runtime_event_normalizer_contract.py")


NORMALIZER_CONTENT = r'''from __future__ import annotations

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
'''


TEST_CONTENT = r'''from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeEventNormalizerContractTest(unittest.TestCase):
    def test_normalizes_flat_event_into_envelope(self) -> None:
        from core.runtime.event_normalizer import normalize_runtime_event_envelope

        event = normalize_runtime_event_envelope(
            {
                "event_type": "execution_guard",
                "runtime_mode": "guard",
                "task_id": "task-1",
                "ok": False,
                "error_text": "blocked",
                "guard_mode": "path_blocked",
            },
            source="test",
        )

        self.assertEqual(event["event_type"], "execution_guard")
        self.assertEqual(event["runtime_phase"], "guard")
        self.assertEqual(event["task_id"], "task-1")
        self.assertEqual(event["source"], "test")
        self.assertIs(event["ok"], False)
        self.assertEqual(event["payload"]["error_text"], "blocked")
        self.assertEqual(event["payload"]["guard_mode"], "path_blocked")

    def test_normalizes_trace_event_data_payload(self) -> None:
        from core.runtime.event_normalizer import normalize_runtime_event_envelope

        event = normalize_runtime_event_envelope(
            {
                "ts": 123,
                "event_type": "status",
                "data": {
                    "task_id": "task-2",
                    "status": "running",
                    "ok": True,
                },
            },
            source="trace",
        )

        self.assertEqual(event["event_type"], "status")
        self.assertEqual(event["runtime_phase"], "runtime")
        self.assertEqual(event["task_id"], "task-2")
        self.assertEqual(event["timestamp"], 123)
        self.assertEqual(event["payload"]["status"], "running")
        self.assertIs(event["ok"], True)

    def test_normalizes_stream_dict(self) -> None:
        from core.runtime.event_normalizer import normalize_runtime_event_stream_envelope

        stream = normalize_runtime_event_stream_envelope(
            {
                "runtime_event_stream": [
                    {"event_type": "first", "ts": 1},
                    {"event_type": "second", "ts": 2},
                ]
            },
            source="stream",
        )

        self.assertEqual(len(stream), 2)
        self.assertEqual(stream[0]["event_type"], "first")
        self.assertEqual(stream[1]["event_type"], "second")
        self.assertEqual(stream[0]["source"], "stream")

    def test_non_dict_event_becomes_unknown_payload(self) -> None:
        from core.runtime.event_normalizer import normalize_runtime_event_envelope

        event = normalize_runtime_event_envelope("bad-event", source="test")

        self.assertEqual(event["event_type"], "unknown")
        self.assertEqual(event["runtime_phase"], "unknown")
        self.assertEqual(event["payload"]["raw"], "bad-event")


if __name__ == "__main__":
    unittest.main()
'''


EVENT_STREAM_IMPORT = '''from core.runtime.event_normalizer import (
    normalize_runtime_event_envelope,
    normalize_runtime_event_stream_envelope,
)

'''


def main() -> None:
    NORMALIZER_PATH.write_text(NORMALIZER_CONTENT, encoding="utf-8")
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")

    if not EVENT_STREAM_PATH.exists():
        raise FileNotFoundError(EVENT_STREAM_PATH)

    source = EVENT_STREAM_PATH.read_text(encoding="utf-8")
    if "normalize_runtime_event_envelope" not in source:
        insert_after = "from typing import Any, Dict, List\n\n"
        if insert_after not in source:
            raise RuntimeError("event_stream import marker not found")
        source = source.replace(insert_after, insert_after + EVENT_STREAM_IMPORT, 1)

    EVENT_STREAM_PATH.write_text(source, encoding="utf-8")

    print("[runtime-event-normalizer-v1] created core/runtime/event_normalizer.py")
    print("[runtime-event-normalizer-v1] updated core/runtime/event_stream.py imports")
    print("[runtime-event-normalizer-v1] created tests/test_runtime_event_normalizer_contract.py")


if __name__ == "__main__":
    main()