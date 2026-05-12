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


def _execute_step(executor: Any, step: Dict[str, Any]) -> Dict[str, Any]:
    if hasattr(executor, "execute_step"):
        method = executor.execute_step
    elif hasattr(executor, "run_step"):
        method = executor.run_step
    else:
        raise AssertionError("StepExecutor has no execute_step/run_step method")

    try:
        return method(step)
    except TypeError:
        return method(step=step)


def _execute_steps(executor: Any, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not hasattr(executor, "execute_steps"):
        raise AssertionError("StepExecutor has no execute_steps method")

    method = executor.execute_steps
    try:
        return method(steps)
    except TypeError:
        return method(steps=steps)


class RuntimeExecutionContractsTest(unittest.TestCase):
    def test_step_executor_unsupported_step_type_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = _make_step_executor(Path(tmp))
            result = _execute_step(executor, {"type": "not_real_step"})

        self.assertIsInstance(result, dict)
        self.assertIs(result.get("ok"), False)
        self.assertEqual(result.get("step_type"), "not_real_step")
        self.assertEqual(result.get("runtime_mode"), "execute")
        self.assertIn("unsupported step type", str(result.get("message", "")))

        error = result.get("error")
        self.assertIsInstance(error, dict)
        self.assertEqual(error.get("type"), "unsupported_step_type")
        self.assertFalse(bool(error.get("retryable")))

        trace = result.get("execution_trace")
        self.assertIsInstance(trace, list)
        self.assertGreaterEqual(len(trace), 1)
        self.assertEqual(trace[0].get("error_type"), "unsupported_step_type")

    def test_step_executor_execute_steps_failure_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = _make_step_executor(Path(tmp))
            result = _execute_steps(
                executor,
                [
                    {"type": "not_real_step"},
                    {"type": "noop", "message": "should not run after failure"},
                ],
            )

        self.assertIsInstance(result, dict)
        self.assertIs(result.get("ok"), False)
        self.assertEqual(result.get("summary"), "step execution failed")
        self.assertIn("unsupported step type", str(result.get("message", "")))
        self.assertEqual(result.get("step_count"), 2)
        self.assertEqual(result.get("completed_steps"), 0)
        self.assertEqual(result.get("failed_step"), 0)

        results = result.get("results")
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 1)
        self.assertFalse(bool(results[0].get("ok")))

        error = result.get("error")
        self.assertIsInstance(error, dict)
        self.assertEqual(error.get("type"), "unsupported_step_type")

        trace = result.get("execution_trace")
        self.assertIsInstance(trace, list)
        self.assertGreaterEqual(len(trace), 1)

    def test_step_executor_execute_steps_empty_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = _make_step_executor(Path(tmp))
            result = _execute_steps(executor, [])

        self.assertIsInstance(result, dict)
        self.assertIs(result.get("ok"), True)
        self.assertEqual(result.get("summary"), "all steps executed")
        self.assertEqual(result.get("message"), "執行完成")
        self.assertEqual(result.get("final_answer"), "執行完成")
        self.assertEqual(result.get("step_count"), 0)
        self.assertEqual(result.get("completed_steps"), 0)
        self.assertIsNone(result.get("failed_step"))
        self.assertEqual(result.get("results"), [])
        self.assertIsNone(result.get("last_result"))
        self.assertIsNone(result.get("error"))
        self.assertEqual(result.get("execution_trace"), [])

    def test_step_executor_lists_apply_patch_handler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = _make_step_executor(Path(tmp))

        handlers = []
        if hasattr(executor, "list_handlers"):
            handlers = list(executor.list_handlers())
        elif hasattr(executor, "handlers"):
            handlers = list(getattr(executor, "handlers", {}).keys())

        self.assertIn("apply_patch", handlers)
        self.assertIn("verify", handlers)
        self.assertIn("read_file", handlers)
        self.assertIn("write_file", handlers)


if __name__ == "__main__":
    unittest.main()
