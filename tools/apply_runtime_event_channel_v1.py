from __future__ import annotations

from pathlib import Path


EVENT_STREAM_PATH = Path("core/runtime/event_stream.py")
TEST_PATH = Path("tests/test_runtime_event_channel_contract.py")


APPEND_BLOCK = r'''


class RuntimeEventChannel:
    """
    Append-only in-memory runtime event channel.

    This is intentionally small:
    - no websocket yet
    - no UI dependency
    - no scheduler dependency
    - stores normalized runtime events only
    """

    def __init__(self) -> None:
        self._events: List[Dict[str, Any]] = []
        self._cursor: int = 0

    def append_event(self, event: Any, *, source: str = "runtime") -> Dict[str, Any]:
        normalized = normalize_runtime_event(event, source=source)
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
            "runtime_mode": "event_channel",
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
            "runtime_mode": "event_channel",
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
'''


def main() -> None:
    if not EVENT_STREAM_PATH.exists():
        raise FileNotFoundError(EVENT_STREAM_PATH)

    source = EVENT_STREAM_PATH.read_text(encoding="utf-8")

    if "class RuntimeEventChannel:" not in source:
        source = source.rstrip() + APPEND_BLOCK + "\n"

    EVENT_STREAM_PATH.write_text(source, encoding="utf-8")
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")

    print("[runtime-event-channel-v1] updated core/runtime/event_stream.py")
    print("[runtime-event-channel-v1] created tests/test_runtime_event_channel_contract.py")


if __name__ == "__main__":
    main()