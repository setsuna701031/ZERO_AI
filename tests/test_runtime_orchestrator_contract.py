from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeOrchestratorContractTest(unittest.TestCase):
    def test_runtime_orchestrator_evaluate_runtime(self) -> None:
        from core.runtime.event_sink import RuntimeEventSink
        from core.runtime.runtime_orchestrator import RuntimeOrchestrator

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            sink = RuntimeEventSink(path)
            sink.append_event({
                "event_type": "status",
                "runtime_mode": "execute",
                "status": "running",
                "task_id": "task-1",
                "timestamp": time.time(),
            })

            orchestrator = RuntimeOrchestrator(path)
            result = orchestrator.evaluate_runtime()

        self.assertEqual(result["runtime_phase"], "runtime_orchestrator")
        self.assertEqual(result["runtime_status"], "running")
        self.assertIn("monitor", result)
        self.assertIn("recovery", result)
        self.assertIn("snapshot", result)
        self.assertIn("state", result)

    def test_runtime_orchestrator_triggers_recovery(self) -> None:
        from core.runtime.event_sink import RuntimeEventSink
        from core.runtime.runtime_orchestrator import RuntimeOrchestrator

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            sink = RuntimeEventSink(path)
            sink.append_event({
                "event_type": "failure",
                "runtime_mode": "repo_state",
                "timestamp": time.time(),
            })

            orchestrator = RuntimeOrchestrator(path)
            should = orchestrator.should_trigger_recovery()

        self.assertTrue(should)

    def test_runtime_orchestrator_does_not_trigger_recovery(self) -> None:
        from core.runtime.event_sink import RuntimeEventSink
        from core.runtime.runtime_orchestrator import RuntimeOrchestrator

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            sink = RuntimeEventSink(path)
            sink.append_event({
                "event_type": "status",
                "runtime_mode": "execute",
                "status": "running",
                "timestamp": time.time(),
            })

            orchestrator = RuntimeOrchestrator(path)
            should = orchestrator.should_trigger_recovery()

        self.assertFalse(should)


if __name__ == "__main__":
    unittest.main()
