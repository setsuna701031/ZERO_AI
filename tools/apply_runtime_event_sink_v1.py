from __future__ import annotations

from pathlib import Path


SINK_PATH = Path("core/runtime/event_sink.py")
TEST_PATH = Path("tests/test_runtime_event_sink_contract.py")


SINK_CONTENT = r'''from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from core.runtime.event_normalizer import normalize_runtime_event_envelope


class RuntimeEventSink:
    """
    Append-only JSONL runtime event sink.

    This is the persistence layer for normalized runtime events.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append_event(self, event: Any, *, source: str = "runtime") -> Dict[str, Any]:
        normalized = normalize_runtime_event_envelope(event, source=source)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(normalized, ensure_ascii=False, sort_keys=True) + "\n")

        return normalized

    def append_events(self, events: Any, *, source: str = "runtime") -> List[Dict[str, Any]]:
        if isinstance(events, dict):
            if isinstance(events.get("runtime_event_stream"), list):
                events = events.get("runtime_event_stream")
            elif isinstance(events.get("events"), list):
                events = events.get("events")
            else:
                events = [events]

        if not isinstance(events, list):
            return []

        appended: List[Dict[str, Any]] = []
        for event in events:
            if isinstance(event, dict):
                appended.append(self.append_event(event, source=source))
        return appended

    def read_events(self, *, limit: int | None = None) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []

        events: List[Dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if not text:
                    continue
                try:
                    item = json.loads(text)
                except Exception:
                    continue
                if isinstance(item, dict):
                    events.append(item)

        if isinstance(limit, int) and limit >= 0:
            return events[-limit:]
        return events

    def snapshot(self, *, limit: int | None = None) -> Dict[str, Any]:
        events = self.read_events(limit=limit)
        return {
            "ok": True,
            "runtime_phase": "event_sink",
            "path": str(self.path),
            "event_count": len(events),
            "events": events,
        }

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
'''


TEST_CONTENT = r'''from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeEventSinkContractTest(unittest.TestCase):
    def test_append_and_read_event(self) -> None:
        from core.runtime.event_sink import RuntimeEventSink

        with tempfile.TemporaryDirectory() as tmp:
            sink = RuntimeEventSink(Path(tmp) / "events.jsonl")
            event = sink.append_event(
                {
                    "event_type": "status",
                    "runtime_mode": "execute",
                    "task_id": "task-1",
                    "status": "running",
                },
                source="test",
            )
            events = sink.read_events()

        self.assertEqual(event["event_type"], "status")
        self.assertEqual(event["runtime_phase"], "execute")
        self.assertEqual(event["task_id"], "task-1")
        self.assertEqual(event["payload"]["status"], "running")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "status")

    def test_append_events_from_runtime_event_stream(self) -> None:
        from core.runtime.event_sink import RuntimeEventSink

        with tempfile.TemporaryDirectory() as tmp:
            sink = RuntimeEventSink(Path(tmp) / "events.jsonl")
            appended = sink.append_events(
                {
                    "runtime_event_stream": [
                        {"event_type": "first", "timestamp": 1},
                        {"event_type": "second", "timestamp": 2},
                    ]
                },
                source="stream",
            )
            snapshot = sink.snapshot()

        self.assertEqual(len(appended), 2)
        self.assertEqual(snapshot["event_count"], 2)
        self.assertEqual([event["event_type"] for event in snapshot["events"]], ["first", "second"])

    def test_limit_and_clear(self) -> None:
        from core.runtime.event_sink import RuntimeEventSink

        with tempfile.TemporaryDirectory() as tmp:
            sink = RuntimeEventSink(Path(tmp) / "events.jsonl")
            sink.append_event({"event_type": "first", "timestamp": 1})
            sink.append_event({"event_type": "second", "timestamp": 2})
            limited = sink.read_events(limit=1)
            sink.clear()
            after_clear = sink.read_events()

        self.assertEqual(len(limited), 1)
        self.assertEqual(limited[0]["event_type"], "second")
        self.assertEqual(after_clear, [])


if __name__ == "__main__":
    unittest.main()
'''


def main() -> None:
    SINK_PATH.write_text(SINK_CONTENT, encoding="utf-8")
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")

    print("[runtime-event-sink-v1] created core/runtime/event_sink.py")
    print("[runtime-event-sink-v1] created tests/test_runtime_event_sink_contract.py")


if __name__ == "__main__":
    main()