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


class RuntimeContractIntegrityTest(unittest.TestCase):
    def _make_step_executor(self, workspace_root: Path) -> Any:
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

    def _execute_steps(self, executor: Any, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        method = executor.execute_steps

        attempts = [
            lambda: method(steps),
            lambda: method(steps=steps),
        ]

        last_error: Exception | None = None
        for call in attempts:
            try:
                result = call()
                self.assertIsInstance(result, dict)
                return result
            except TypeError as exc:
                last_error = exc

        raise AssertionError(f"Unable to call execute_steps: {last_error}")

    def _assert_batch_tier1_contract_fields_exist(self, payload: Dict[str, Any]) -> None:
        for field in [
            "execution_trace",
            "results",
            "final_answer",
            "error",
        ]:
            self.assertIn(field, payload)

    def _assert_step_runtime_shape(self, payload: Dict[str, Any]) -> None:
        for field in [
            "ok",
            "message",
            "final_answer",
            "error",
            "execution_trace",
            "runtime_mode",
            "step_type",
            "step_index",
            "step_count",
            "result",
        ]:
            self.assertIn(field, payload)

    def _assert_trace_runtime_shape(self, payload: Dict[str, Any]) -> None:
        for field in [
            "ok",
            "message",
            "final_answer",
            "error_type",
            "runtime_mode",
            "step_type",
            "step_index",
            "attempts",
            "max_attempts",
            "retry_used",
        ]:
            self.assertIn(field, payload)

    def test_successful_runtime_contract_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = self._make_step_executor(Path(tmp))

            result = self._execute_steps(
                executor,
                [
                    {
                        "type": "write_file",
                        "path": "workspace/shared/runtime_contract_ok.txt",
                        "content": "RUNTIME_OK",
                    },
                    {
                        "type": "read_file",
                        "path": "workspace/shared/runtime_contract_ok.txt",
                    },
                    {
                        "type": "verify",
                        "path": "workspace/shared/runtime_contract_ok.txt",
                        "contains": "RUNTIME_OK",
                    },
                ],
            )

        self._assert_batch_tier1_contract_fields_exist(result)

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("summary"), "all steps executed")
        self.assertEqual(result.get("message"), "RUNTIME_OK")
        self.assertEqual(result.get("final_answer"), "RUNTIME_OK")
        self.assertEqual(result.get("completed_steps"), 3)
        self.assertEqual(result.get("failed_step"), None)
        self.assertEqual(result.get("error"), None)

        execution_trace = result.get("execution_trace")
        self.assertIsInstance(execution_trace, list)
        self.assertEqual(len(execution_trace), 3)

        for trace_item in execution_trace:
            self.assertIsInstance(trace_item, dict)
            self._assert_trace_runtime_shape(trace_item)

        results = result.get("results")
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 3)

        for item in results:
            self.assertIsInstance(item, dict)
            self._assert_step_runtime_shape(item)

    def test_failed_runtime_contract_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = self._make_step_executor(Path(tmp))

            result = self._execute_steps(
                executor,
                [
                    {
                        "type": "not_real_step",
                    },
                ],
            )

        self._assert_batch_tier1_contract_fields_exist(result)

        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("summary"), "step execution failed")
        self.assertEqual(result.get("message"), "unsupported step type: not_real_step")
        self.assertEqual(result.get("final_answer"), "unsupported step type: not_real_step")
        self.assertEqual(result.get("completed_steps"), 0)
        self.assertEqual(result.get("failed_step"), 0)

        error = result.get("error")
        self.assertIsInstance(error, dict)
        self.assertEqual(error.get("type"), "unsupported_step_type")

        trace = result.get("execution_trace")
        self.assertIsInstance(trace, list)
        self.assertGreaterEqual(len(trace), 1)

        for trace_item in trace:
            self.assertIsInstance(trace_item, dict)
            self._assert_trace_runtime_shape(trace_item)

        results = result.get("results")
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 1)

        for item in results:
            self.assertIsInstance(item, dict)
            self._assert_step_runtime_shape(item)

    def test_empty_runtime_contract_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = self._make_step_executor(Path(tmp))
            result = self._execute_steps(executor, [])

        self._assert_batch_tier1_contract_fields_exist(result)

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("summary"), "all steps executed")
        self.assertEqual(result.get("message"), "執行完成")
        self.assertEqual(result.get("final_answer"), "執行完成")
        self.assertEqual(result.get("completed_steps"), 0)
        self.assertEqual(result.get("failed_step"), None)
        self.assertEqual(result.get("results"), [])
        self.assertEqual(result.get("execution_trace"), [])
        self.assertEqual(result.get("error"), None)


if __name__ == "__main__":
    unittest.main()
