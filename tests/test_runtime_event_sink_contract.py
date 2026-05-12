from __future__ import annotations

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
