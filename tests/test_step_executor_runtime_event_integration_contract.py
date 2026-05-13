from __future__ import annotations

import inspect
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _make_step_executor(workspace_root: Path) -> Any:
    from core.runtime.step_executor import StepExecutor

    signature = inspect.signature(StepExecutor)
    kwargs: Dict[str, Any] = {}

    if "workspace_root" in signature.parameters:
        kwargs["workspace_root"] = workspace_root
    if "workspace_dir" in signature.parameters:
        kwargs["workspace_dir"] = workspace_root
    if "runtime_store" in signature.parameters:
        kwargs["runtime_store"] = None
    if "tool_registry" in signature.parameters:
        kwargs["tool_registry"] = None
    if "llm_client" in signature.parameters:
        kwargs["llm_client"] = None
    if "debug" in signature.parameters:
        kwargs["debug"] = False

    return StepExecutor(**kwargs)


def _execute_steps(executor: Any, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not hasattr(executor, "execute_steps"):
        raise AssertionError("StepExecutor has no execute_steps method")

    method = executor.execute_steps
    try:
        return method(steps)
    except TypeError:
        return method(steps=steps)


class StepExecutorRuntimeEventIntegrationContractTest(unittest.TestCase):
    def test_success_execute_steps_has_runtime_event_stream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = _make_step_executor(Path(tmp))
            result = _execute_steps(executor, [{"type": "noop", "message": "done"}])

        stream = result.get("runtime_event_stream")

        self.assertIsInstance(stream, list)
        self.assertGreaterEqual(len(stream), 1)
        self.assertEqual(stream[0].get("source"), "step_executor")
        self.assertIn("event_type", stream[0])
        self.assertIn("runtime_phase", stream[0])
        self.assertIn("payload", stream[0])

    def test_failed_execute_steps_has_runtime_event_stream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = _make_step_executor(Path(tmp))
            result = _execute_steps(executor, [{"type": "not_real_step"}])

        stream = result.get("runtime_event_stream")

        self.assertIsInstance(stream, list)
        self.assertGreaterEqual(len(stream), 1)
        self.assertEqual(stream[0].get("source"), "step_executor")
        self.assertFalse(result.get("ok"))

    def test_runtime_event_stream_matches_adapter_execution_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = _make_step_executor(Path(tmp))
            result = _execute_steps(executor, [{"type": "noop", "message": "done"}])

        adapter = result.get("adapter_payload")
        stream = result.get("runtime_event_stream")

        self.assertIsInstance(adapter, dict)
        self.assertIsInstance(adapter.get("execution_trace"), list)
        self.assertIsInstance(stream, list)
        self.assertEqual(len(stream), len(adapter.get("execution_trace")))


if __name__ == "__main__":
    unittest.main()
