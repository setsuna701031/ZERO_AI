from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TraceRuntimeAggregateAdapterContractTest(unittest.TestCase):
    def test_trace_runtime_payload_gets_adapter_payload(self) -> None:
        from core.runtime.trace_runtime import TraceRuntime

        runtime = TraceRuntime()
        payload: Dict[str, Any] = {
            "ok": True,
            "message": "trace ok",
            "final_answer": "trace ok",
            "runtime_mode": "trace",
            "execution_trace": [{"event": "step", "ok": True}],
        }

        adapted = runtime.attach_adapter_payload(copy.deepcopy(payload))
        adapter = adapted.get("adapter_payload")

        self.assertIsInstance(adapter, dict)
        self.assertIs(adapter.get("ok"), True)
        self.assertEqual(adapter.get("message"), "trace ok")
        self.assertEqual(adapter.get("final_answer"), "trace ok")
        self.assertEqual(adapter.get("runtime_mode"), "trace")
        self.assertEqual(adapter.get("execution_trace"), [{"event": "step", "ok": True}])
        self.assertIsInstance(adapter.get("raw"), dict)

    def test_trace_runtime_failure_payload_gets_error_fields(self) -> None:
        from core.runtime.trace_runtime import TraceRuntime

        runtime = TraceRuntime()
        payload: Dict[str, Any] = {
            "ok": False,
            "message": "trace failed",
            "final_answer": "trace failed",
            "runtime_mode": "trace",
            "error": {
                "type": "trace_save_failed",
                "message": "disk error",
            },
        }

        adapted = runtime.attach_adapter_payload(copy.deepcopy(payload))
        adapter = adapted.get("adapter_payload")

        self.assertIsInstance(adapter, dict)
        self.assertIs(adapter.get("ok"), False)
        self.assertEqual(adapter.get("error_type"), "trace_save_failed")
        self.assertEqual(adapter.get("error_text"), "disk error")
        self.assertEqual(adapter.get("runtime_mode"), "trace")

    def test_trace_to_adapter_payload_uses_execution_trace_events(self) -> None:
        from core.runtime.trace_runtime import TraceRuntime
        from core.tools.execution_trace import ExecutionTrace

        runtime = TraceRuntime()
        trace = ExecutionTrace()
        trace.add_step_event(
            task_id="task-1",
            step_index=1,
            step={"type": "respond"},
            ok=True,
            result={"ok": True, "message": "done"},
            error="",
            tick=1,
        )

        adapted = runtime.trace_to_adapter_payload(trace)
        adapter = adapted.get("adapter_payload")

        self.assertIsInstance(adapter, dict)
        self.assertIs(adapter.get("ok"), True)
        self.assertEqual(adapter.get("runtime_mode"), "trace")
        self.assertEqual(adapted.get("event_count"), 1)
        self.assertEqual(len(adapter.get("execution_trace")), 1)
        self.assertIsInstance(adapter.get("last_result"), dict)

    def test_existing_adapter_payload_is_preserved(self) -> None:
        from core.runtime.trace_runtime import TraceRuntime

        runtime = TraceRuntime()
        payload: Dict[str, Any] = {
            "ok": True,
            "adapter_payload": {
                "ok": True,
                "message": "already adapted",
            },
        }

        adapted = runtime.attach_adapter_payload(payload)

        self.assertIs(adapted, payload)
        self.assertEqual(adapted["adapter_payload"]["message"], "already adapted")


if __name__ == "__main__":
    unittest.main()
