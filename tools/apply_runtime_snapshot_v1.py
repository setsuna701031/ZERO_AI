from __future__ import annotations

from pathlib import Path


SNAPSHOT_PATH = Path("core/runtime/runtime_snapshot.py")
TEST_PATH = Path("tests/test_runtime_snapshot_contract.py")


SNAPSHOT_CONTENT = r'''from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from core.runtime.event_replay import RuntimeEventReplay


class RuntimeSnapshot:
    def __init__(self, path: str | Path) -> None:
        self.replay = RuntimeEventReplay(path)

    def build_snapshot(self) -> Dict[str, Any]:
        events = self.replay.events()
        latest = self.replay.latest()

        recent_events = self.replay.tail(10)

        failure_events = [
            event
            for event in events
            if str(event.get("event_type") or "").lower() in {"failure", "error", "guard_blocked"}
        ]

        active_task = ""
        for event in reversed(events):
            candidate = str(event.get("task_id") or "").strip()
            if candidate:
                active_task = candidate
                break

        runtime_status = self._derive_runtime_status(
            latest=latest,
            failure_events=failure_events,
        )

        return {
            "ok": True,
            "runtime_phase": "snapshot",
            "runtime_status": runtime_status,
            "active_task": active_task,
            "last_event": latest,
            "recent_events": recent_events,
            "failure_state": failure_events[-1] if failure_events else {},
            "event_count": len(events),
        }

    def _derive_runtime_status(
        self,
        *,
        latest: Dict[str, Any],
        failure_events: List[Dict[str, Any]],
    ) -> str:
        if failure_events:
            return "degraded"

        status = str(
            latest.get("status")
            or latest.get("payload", {}).get("status")
            or ""
        ).strip().lower()

        if status in {"running", "queued", "blocked"}:
            return status

        if latest:
            return "healthy"

        return "idle"
'''


TEST_CONTENT = r'''from __future__ import annotations

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
'''


def main() -> None:
    SNAPSHOT_PATH.write_text(SNAPSHOT_CONTENT, encoding="utf-8")
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")

    print("[runtime-snapshot-v1] created core/runtime/runtime_snapshot.py")
    print("[runtime-snapshot-v1] created tests/test_runtime_snapshot_contract.py")


if __name__ == "__main__":
    main()