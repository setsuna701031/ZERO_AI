from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeSnapshotContractTest(unittest.TestCase):
    def test_snapshot_reports_latest_event(self) -> None:
        from core.runtime.event_sink import RuntimeEventSink
        from core.runtime.runtime_snapshot import RuntimeSnapshot

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"

            sink = RuntimeEventSink(path)
            sink.append_event({
                "event_type": "status",
                "status": "running",
                "task_id": "task-123",
                "timestamp": 1,
            })

            snapshot = RuntimeSnapshot(path).build_snapshot()

        self.assertEqual(snapshot["runtime_status"], "running")
        self.assertEqual(snapshot["active_task"], "task-123")
        self.assertEqual(snapshot["event_count"], 1)

    def test_snapshot_detects_failure_state(self) -> None:
        from core.runtime.event_sink import RuntimeEventSink
        from core.runtime.runtime_snapshot import RuntimeSnapshot

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"

            sink = RuntimeEventSink(path)
            sink.append_event({
                "event_type": "failure",
                "task_id": "task-x",
                "timestamp": 2,
            })

            snapshot = RuntimeSnapshot(path).build_snapshot()

        self.assertEqual(snapshot["runtime_status"], "degraded")
        self.assertEqual(snapshot["failure_state"]["event_type"], "failure")

    def test_snapshot_recent_events_tail(self) -> None:
        from core.runtime.event_sink import RuntimeEventSink
        from core.runtime.runtime_snapshot import RuntimeSnapshot

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"

            sink = RuntimeEventSink(path)

            for i in range(15):
                sink.append_event({
                    "event_type": f"event-{i}",
                    "timestamp": i,
                })

            snapshot = RuntimeSnapshot(path).build_snapshot()

        self.assertEqual(len(snapshot["recent_events"]), 10)
        self.assertEqual(snapshot["recent_events"][-1]["event_type"], "event-14")


if __name__ == "__main__":
    unittest.main()
