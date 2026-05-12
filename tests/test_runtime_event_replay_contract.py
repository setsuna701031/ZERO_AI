from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeEventReplayContractTest(unittest.TestCase):
    def test_latest_and_tail(self) -> None:
        from core.runtime.event_replay import RuntimeEventReplay
        from core.runtime.event_sink import RuntimeEventSink

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            sink = RuntimeEventSink(path)
            sink.append_event({"event_type": "first", "timestamp": 1})
            sink.append_event({"event_type": "second", "timestamp": 2})

            replay = RuntimeEventReplay(path)
            latest = replay.latest()
            tail = replay.tail(1)

        self.assertEqual(latest["event_type"], "second")
        self.assertEqual(len(tail), 1)
        self.assertEqual(tail[0]["event_type"], "second")

    def test_filter_by_phase_and_task(self) -> None:
        from core.runtime.event_replay import RuntimeEventReplay
        from core.runtime.event_sink import RuntimeEventSink

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            sink = RuntimeEventSink(path)
            sink.append_event({"event_type": "step", "runtime_mode": "execute", "task_id": "task-1"})
            sink.append_event({"event_type": "guard", "runtime_mode": "guard", "task_id": "task-2"})
            sink.append_event({"event_type": "status", "runtime_mode": "execute", "task_id": "task-1"})

            replay = RuntimeEventReplay(path)
            execute_events = replay.filter_by_phase("execute")
            task_events = replay.filter_by_task("task-1")

        self.assertEqual(len(execute_events), 2)
        self.assertEqual(len(task_events), 2)

    def test_timeline_sorts_by_timestamp(self) -> None:
        from core.runtime.event_replay import RuntimeEventReplay
        from core.runtime.event_sink import RuntimeEventSink

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            sink = RuntimeEventSink(path)
            sink.append_event({"event_type": "third", "timestamp": 3})
            sink.append_event({"event_type": "first", "timestamp": 1})
            sink.append_event({"event_type": "second", "timestamp": 2})

            replay = RuntimeEventReplay(path)
            timeline = replay.timeline()

        self.assertEqual(timeline["event_count"], 3)
        self.assertEqual([event["event_type"] for event in timeline["events"]], ["first", "second", "third"])


if __name__ == "__main__":
    unittest.main()
