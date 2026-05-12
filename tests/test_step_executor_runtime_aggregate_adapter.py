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


class StepExecutorRuntimeAggregateAdapterTest(unittest.TestCase):
    def test_failed_execute_steps_has_aggregate_adapter_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = _make_step_executor(Path(tmp))
            result = _execute_steps(
                executor,
                [
                    {"type": "not_real_step"},
                    {"type": "respond", "message": "should not run"},
                ],
            )

        adapter = result.get("adapter_payload")

        self.assertIsInstance(adapter, dict)
        self.assertIs(adapter.get("ok"), False)
        self.assertEqual(adapter.get("runtime_mode"), "")
        self.assertIsInstance(adapter.get("message"), str)
        self.assertIsInstance(adapter.get("final_answer"), str)
        self.assertIsInstance(adapter.get("execution_trace"), list)
        self.assertIsInstance(adapter.get("last_result"), dict)

    def test_failed_execute_steps_adapter_preserves_error_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = _make_step_executor(Path(tmp))
            result = _execute_steps(executor, [{"type": "not_real_step"}])

        adapter = result.get("adapter_payload")

        self.assertIsInstance(adapter, dict)
        self.assertEqual(adapter.get("error_type"), "unsupported_step_type")
        self.assertIn("unsupported step type", str(adapter.get("error_text") or ""))

    def test_empty_execute_steps_has_aggregate_adapter_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = _make_step_executor(Path(tmp))
            result = _execute_steps(executor, [])

        adapter = result.get("adapter_payload")

        self.assertIsInstance(adapter, dict)
        self.assertIs(adapter.get("ok"), True)
        self.assertEqual(adapter.get("message"), result.get("message"))
        self.assertEqual(adapter.get("final_answer"), result.get("final_answer"))
        self.assertEqual(adapter.get("execution_trace"), [])
        self.assertIsNone(adapter.get("last_result"))

    def test_success_execute_steps_has_aggregate_adapter_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = _make_step_executor(Path(tmp))
            result = _execute_steps(
                executor,
                [{"type": "respond", "message": "done"}],
            )

        adapter = result.get("adapter_payload")

        self.assertIsInstance(adapter, dict)
        self.assertIs(adapter.get("ok"), True)
        self.assertIsInstance(adapter.get("message"), str)
        self.assertIsInstance(adapter.get("final_answer"), str)
        self.assertIsInstance(adapter.get("execution_trace"), list)


if __name__ == "__main__":
    unittest.main()