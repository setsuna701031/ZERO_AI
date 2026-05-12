from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeEventChannelContractTest(unittest.TestCase):
    def test_append_event_assigns_cursor(self) -> None:
        from core.runtime.event_stream import RuntimeEventChannel

        channel = RuntimeEventChannel()
        event = channel.append_event(
            {
                "event_type": "status",
                "task_id": "task-1",
                "status": "running",
                "ok": True,
            },
            source="test",
        )

        self.assertEqual(event.get("cursor"), 1)
        self.assertEqual(event.get("event_type"), "status")
        self.assertEqual(event.get("task_id"), "task-1")
        self.assertEqual(event.get("source"), "test")
        self.assertEqual(channel.latest_cursor(), 1)

    def test_snapshot_and_events_since(self) -> None:
        from core.runtime.event_stream import RuntimeEventChannel

        channel = RuntimeEventChannel()
        channel.append_event({"event_type": "first"}, source="test")
        channel.append_event({"event_type": "second"}, source="test")
        channel.append_event({"event_type": "third"}, source="test")

        snapshot = channel.snapshot()
        since_one = channel.events_since(1)

        self.assertEqual(snapshot.get("cursor"), 3)
        self.assertEqual(snapshot.get("event_count"), 3)
        self.assertEqual(len(snapshot.get("events")), 3)

        self.assertEqual(since_one.get("from_cursor"), 1)
        self.assertEqual(since_one.get("event_count"), 2)
        self.assertEqual([event.get("event_type") for event in since_one.get("events")], ["second", "third"])

    def test_append_events_accepts_payload_runtime_event_stream(self) -> None:
        from core.runtime.event_stream import RuntimeEventChannel

        channel = RuntimeEventChannel()
        appended = channel.append_events(
            {
                "runtime_event_stream": [
                    {"event_type": "guard", "ok": True},
                    {"event_type": "failure", "ok": False},
                ]
            },
            source="payload",
        )

        self.assertEqual(len(appended), 2)
        self.assertEqual(channel.latest_cursor(), 2)
        self.assertEqual([event.get("cursor") for event in appended], [1, 2])

    def test_clear_resets_channel(self) -> None:
        from core.runtime.event_stream import RuntimeEventChannel

        channel = RuntimeEventChannel()
        channel.append_event({"event_type": "status"}, source="test")
        channel.clear()

        self.assertEqual(channel.latest_cursor(), 0)
        self.assertEqual(channel.snapshot().get("event_count"), 0)


if __name__ == "__main__":
    unittest.main()
