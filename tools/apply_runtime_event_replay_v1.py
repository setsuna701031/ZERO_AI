from __future__ import annotations

from pathlib import Path


REPLAY_PATH = Path("core/runtime/event_replay.py")
TEST_PATH = Path("tests/test_runtime_event_replay_contract.py")


REPLAY_CONTENT = r'''from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from core.runtime.event_normalizer import normalize_runtime_event_stream_envelope
from core.runtime.event_sink import RuntimeEventSink


class RuntimeEventReplay:
    def __init__(self, path: str | Path) -> None:
        self.sink = RuntimeEventSink(path)

    def events(self) -> List[Dict[str, Any]]:
        return normalize_runtime_event_stream_envelope(self.sink.read_events(), source="event_replay")

    def latest(self) -> Dict[str, Any]:
        events = self.events()
        return events[-1] if events else {}

    def tail(self, limit: int = 20) -> List[Dict[str, Any]]:
        try:
            n = max(0, int(limit))
        except Exception:
            n = 20
        return self.events()[-n:] if n else []

    def filter_by_phase(self, runtime_phase: str) -> List[Dict[str, Any]]:
        phase = str(runtime_phase or "").strip()
        return [event for event in self.events() if str(event.get("runtime_phase") or "") == phase]

    def filter_by_task(self, task_id: str) -> List[Dict[str, Any]]:
        target = str(task_id or "").strip()
        return [event for event in self.events() if str(event.get("task_id") or "") == target]

    def timeline(self) -> Dict[str, Any]:
        events = sorted(self.events(), key=lambda item: float(item.get("timestamp") or 0))
        return {
            "ok": True,
            "runtime_phase": "event_replay",
            "event_count": len(events),
            "events": events,
        }
'''


TEST_CONTENT = r'''from __future__ import annotations

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
'''


def main() -> None:
    REPLAY_PATH.write_text(REPLAY_CONTENT, encoding="utf-8")
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")

    print("[runtime-event-replay-v1] created core/runtime/event_replay.py")
    print("[runtime-event-replay-v1] created tests/test_runtime_event_replay_contract.py")


if __name__ == "__main__":
    main()