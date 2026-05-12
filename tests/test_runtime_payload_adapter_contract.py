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


class RuntimePayloadAdapterContractTest(unittest.TestCase):
    def test_single_step_failure_payload_has_stable_runtime_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = _make_step_executor(Path(tmp))
            result = _execute_step(executor, {"type": "not_real_step"})

        self.assertIsInstance(result, dict)
        self.assertIs(result.get("ok"), False)
        self.assertIsInstance(result.get("message"), str)
        self.assertIsInstance(result.get("final_answer"), str)

        error = result.get("error")
        self.assertIsInstance(error, dict)
        self.assertIsInstance(error.get("type"), str)

        trace = result.get("execution_trace")
        self.assertIsInstance(trace, list)
        self.assertGreaterEqual(len(trace), 1)
        self.assertIsInstance(trace[0], dict)
        self.assertIn("step_type", trace[0])
        self.assertIn("ok", trace[0])

    def test_multi_step_failure_payload_has_stable_runtime_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = _make_step_executor(Path(tmp))
            result = _execute_steps(
                executor,
                [
                    {"type": "not_real_step"},
                    {"type": "noop", "message": "should not run"},
                ],
            )

        self.assertIsInstance(result, dict)
        self.assertIs(result.get("ok"), False)
        self.assertIsInstance(result.get("message"), str)
        self.assertIsInstance(result.get("final_answer"), str)
        self.assertEqual(result.get("step_count"), 2)
        self.assertEqual(result.get("completed_steps"), 0)
        self.assertEqual(result.get("failed_step"), 0)

        results = result.get("results")
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], dict)

        last_result = result.get("last_result")
        self.assertIsInstance(last_result, dict)
        self.assertIs(last_result.get("ok"), False)

        trace = result.get("execution_trace")
        self.assertIsInstance(trace, list)
        self.assertGreaterEqual(len(trace), 1)

    def test_empty_multi_step_payload_has_stable_runtime_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = _make_step_executor(Path(tmp))
            result = _execute_steps(executor, [])

        self.assertIsInstance(result, dict)
        self.assertIs(result.get("ok"), True)
        self.assertIsInstance(result.get("message"), str)
        self.assertIsInstance(result.get("final_answer"), str)
        self.assertEqual(result.get("step_count"), 0)
        self.assertEqual(result.get("completed_steps"), 0)
        self.assertIsNone(result.get("failed_step"))
        self.assertEqual(result.get("results"), [])
        self.assertIsNone(result.get("last_result"))
        self.assertIsNone(result.get("error"))
        self.assertEqual(result.get("execution_trace"), [])

    def test_runtime_payload_normalizer_can_read_step_executor_failure_payload(self) -> None:
        from core.runtime.payload_normalizer import normalize_runtime_payload

        with tempfile.TemporaryDirectory() as tmp:
            executor = _make_step_executor(Path(tmp))
            result = _execute_step(executor, {"type": "not_real_step"})

        normalized = normalize_runtime_payload(result)

        self.assertIs(normalized.ok, False)
        self.assertIsInstance(normalized.text, str)
        self.assertIsInstance(normalized.message, str)
        self.assertIsInstance(normalized.final_answer, str)
        self.assertIsInstance(normalized.error_text, str)
        self.assertEqual(normalized.error_type, "unsupported_step_type")

    def test_runtime_payload_normalizer_can_read_execute_steps_failure_payload(self) -> None:
        from core.runtime.payload_normalizer import normalize_runtime_payload

        with tempfile.TemporaryDirectory() as tmp:
            executor = _make_step_executor(Path(tmp))
            result = _execute_steps(executor, [{"type": "not_real_step"}])

        normalized = normalize_runtime_payload(result)

        self.assertIs(normalized.ok, False)
        self.assertIsInstance(normalized.text, str)
        self.assertIsInstance(normalized.message, str)
        self.assertIsInstance(normalized.final_answer, str)
        self.assertIsInstance(normalized.error_text, str)
        self.assertEqual(normalized.error_type, "unsupported_step_type")


if __name__ == "__main__":
    unittest.main()