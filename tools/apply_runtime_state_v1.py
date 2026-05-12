from __future__ import annotations

from pathlib import Path


STATE_PATH = Path("core/runtime/runtime_state.py")
TEST_PATH = Path("tests/test_runtime_state_contract.py")


STATE_CONTENT = r'''from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from core.runtime.runtime_snapshot import RuntimeSnapshot


class RuntimeState:
    def __init__(self, event_log_path: str | Path) -> None:
        self.snapshot = RuntimeSnapshot(event_log_path)

    def aggregate(self) -> Dict[str, Any]:
        snapshot = self.snapshot.build_snapshot()
        events = snapshot.get("recent_events", [])
        if not isinstance(events, list):
            events = []

        return {
            "ok": bool(snapshot.get("ok", True)),
            "runtime_phase": "runtime_state",
            "runtime_status": self.current_status(snapshot=snapshot),
            "active_runtime": self.active_runtime(events=events),
            "active_task": str(snapshot.get("active_task") or ""),
            "last_event": snapshot.get("last_event") if isinstance(snapshot.get("last_event"), dict) else {},
            "last_failure": self.last_failure(snapshot=snapshot),
            "health_report": self.health_report(snapshot=snapshot),
            "event_count": int(snapshot.get("event_count", 0) or 0),
            "recent_events": events,
        }

    def current_status(self, *, snapshot: Dict[str, Any] | None = None) -> str:
        data = snapshot if isinstance(snapshot, dict) else self.snapshot.build_snapshot()
        return str(data.get("runtime_status") or "idle")

    def active_runtime(self, *, events: List[Dict[str, Any]] | None = None) -> str:
        source = events if isinstance(events, list) else self.snapshot.build_snapshot().get("recent_events", [])
        if not isinstance(source, list):
            return ""

        for event in reversed(source):
            if not isinstance(event, dict):
                continue
            phase = str(event.get("runtime_phase") or "").strip()
            if phase:
                return phase

        return ""

    def last_failure(self, *, snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
        data = snapshot if isinstance(snapshot, dict) else self.snapshot.build_snapshot()
        failure = data.get("failure_state")
        return failure if isinstance(failure, dict) else {}

    def health_report(self, *, snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
        data = snapshot if isinstance(snapshot, dict) else self.snapshot.build_snapshot()
        status = str(data.get("runtime_status") or "idle").strip().lower()
        failure = data.get("failure_state")

        degraded = bool(failure) or status in {"degraded", "failed", "error", "blocked"}

        return {
            "ok": not degraded,
            "status": status or "idle",
            "degraded": degraded,
            "event_count": int(data.get("event_count", 0) or 0),
            "active_task": str(data.get("active_task") or ""),
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


class RuntimeStateContractTest(unittest.TestCase):
    def test_runtime_state_aggregate_healthy(self) -> None:
        from core.runtime.event_sink import RuntimeEventSink
        from core.runtime.runtime_state import RuntimeState

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            sink = RuntimeEventSink(path)
            sink.append_event({
                "event_type": "status",
                "runtime_mode": "execute",
                "task_id": "task-1",
                "status": "running",
                "timestamp": 1,
            })

            state = RuntimeState(path).aggregate()

        self.assertEqual(state["runtime_phase"], "runtime_state")
        self.assertEqual(state["runtime_status"], "running")
        self.assertEqual(state["active_runtime"], "execute")
        self.assertEqual(state["active_task"], "task-1")
        self.assertTrue(state["health_report"]["ok"])

    def test_runtime_state_detects_failure(self) -> None:
        from core.runtime.event_sink import RuntimeEventSink
        from core.runtime.runtime_state import RuntimeState

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            sink = RuntimeEventSink(path)
            sink.append_event({
                "event_type": "failure",
                "runtime_mode": "repo_state",
                "task_id": "task-x",
                "timestamp": 1,
            })

            state = RuntimeState(path).aggregate()

        self.assertEqual(state["runtime_status"], "degraded")
        self.assertEqual(state["last_failure"]["event_type"], "failure")
        self.assertFalse(state["health_report"]["ok"])
        self.assertTrue(state["health_report"]["degraded"])

    def test_runtime_state_idle_without_events(self) -> None:
        from core.runtime.runtime_state import RuntimeState

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            state = RuntimeState(path).aggregate()

        self.assertEqual(state["runtime_status"], "idle")
        self.assertEqual(state["active_runtime"], "")
        self.assertEqual(state["event_count"], 0)
        self.assertTrue(state["health_report"]["ok"])


if __name__ == "__main__":
    unittest.main()
'''


def main() -> None:
    STATE_PATH.write_text(STATE_CONTENT, encoding="utf-8")
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")

    print("[runtime-state-v1] created core/runtime/runtime_state.py")
    print("[runtime-state-v1] created tests/test_runtime_state_contract.py")


if __name__ == "__main__":
    main()