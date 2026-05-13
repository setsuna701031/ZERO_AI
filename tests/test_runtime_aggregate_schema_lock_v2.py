from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeAggregateSchemaLockV2Test(unittest.TestCase):
    def test_runtime_aggregate_schema_stack_is_consistent(self) -> None:
        from core.runtime.event_sink import RuntimeEventSink
        from core.runtime.runtime_orchestrator import RuntimeOrchestrator

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            sink = RuntimeEventSink(path)

            sink.append_event({
                "event_type": "status",
                "runtime_mode": "execute",
                "task_id": "task-schema",
                "status": "running",
                "timestamp": time.time(),
            })

            result = RuntimeOrchestrator(path).evaluate_runtime()

        self.assertEqual(result["runtime_phase"], "runtime_orchestrator")
        self.assertIn("runtime_status", result)
        self.assertIn("monitor", result)
        self.assertIn("recovery", result)
        self.assertIn("snapshot", result)
        self.assertIn("state", result)

        state = result["state"]
        snapshot = result["snapshot"]
        recovery = result["recovery"]
        monitor = result["monitor"]

        self.assertEqual(state["runtime_phase"], "runtime_state")
        self.assertIn("runtime_status", state)
        self.assertIn("active_runtime", state)
        self.assertIn("health_report", state)
        self.assertIn("recent_events", state)

        self.assertEqual(snapshot["runtime_phase"], "snapshot")
        self.assertIn("last_event", snapshot)
        self.assertIn("recent_events", snapshot)
        self.assertIn("event_count", snapshot)

        self.assertEqual(recovery["runtime_phase"], "runtime_recovery")
        self.assertIn("recovery_required", recovery)
        self.assertIn("recovery_blocked", recovery)
        self.assertIn("action", recovery)

        self.assertEqual(monitor["runtime_phase"], "runtime_monitor")
        self.assertIn("alerts", monitor)
        self.assertIn("degraded", monitor)
        self.assertIn("stalled", monitor)

    def test_step_executor_runtime_schema_has_adapter_and_event_stream(self) -> None:
        import inspect
        from core.runtime.step_executor import StepExecutor

        signature = inspect.signature(StepExecutor)
        kwargs = {}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            if "workspace_root" in signature.parameters:
                kwargs["workspace_root"] = root
            if "workspace_dir" in signature.parameters:
                kwargs["workspace_dir"] = root
            if "runtime_store" in signature.parameters:
                kwargs["runtime_store"] = None
            if "tool_registry" in signature.parameters:
                kwargs["tool_registry"] = None
            if "llm_client" in signature.parameters:
                kwargs["llm_client"] = None
            if "debug" in signature.parameters:
                kwargs["debug"] = False

            executor = StepExecutor(**kwargs)
            result = executor.execute_steps([{"type": "noop", "message": "schema ok"}])

        adapter = result.get("adapter_payload")
        stream = result.get("runtime_event_stream")

        self.assertIsInstance(adapter, dict)
        self.assertIn("ok", adapter)
        self.assertIn("message", adapter)
        self.assertIn("final_answer", adapter)
        self.assertIn("execution_trace", adapter)

        self.assertIsInstance(stream, list)
        self.assertGreaterEqual(len(stream), 1)

        event = stream[0]
        self.assertIn("event_type", event)
        self.assertIn("runtime_phase", event)
        self.assertIn("timestamp", event)
        self.assertIn("payload", event)

    def test_failure_path_still_produces_locked_runtime_schema(self) -> None:
        import inspect
        from core.runtime.step_executor import StepExecutor

        signature = inspect.signature(StepExecutor)
        kwargs = {}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            if "workspace_root" in signature.parameters:
                kwargs["workspace_root"] = root
            if "workspace_dir" in signature.parameters:
                kwargs["workspace_dir"] = root
            if "runtime_store" in signature.parameters:
                kwargs["runtime_store"] = None
            if "tool_registry" in signature.parameters:
                kwargs["tool_registry"] = None
            if "llm_client" in signature.parameters:
                kwargs["llm_client"] = None
            if "debug" in signature.parameters:
                kwargs["debug"] = False

            executor = StepExecutor(**kwargs)
            result = executor.execute_steps([{"type": "not_real_step"}])

        self.assertFalse(result.get("ok"))

        adapter = result.get("adapter_payload")
        stream = result.get("runtime_event_stream")

        self.assertIsInstance(adapter, dict)
        self.assertIsInstance(stream, list)
        self.assertGreaterEqual(len(stream), 1)

        event = stream[0]
        self.assertIn("event_type", event)
        self.assertIn("runtime_phase", event)
        self.assertIn("payload", event)


if __name__ == "__main__":
    unittest.main()
