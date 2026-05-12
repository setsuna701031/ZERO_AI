from __future__ import annotations

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
