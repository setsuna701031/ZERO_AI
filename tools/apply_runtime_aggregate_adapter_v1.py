from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STEP_EXECUTOR_PATH = PROJECT_ROOT / "core" / "runtime" / "step_executor.py"
TEST_PATH = PROJECT_ROOT / "tests" / "test_step_executor_runtime_aggregate_adapter.py"


OLD_FAILURE_RETURN = '''                return {
                    "ok": False,
                    "summary": "step execution failed",
                    "message": self._extract_step_message(result, failed=True),
                    "final_answer": self._extract_step_final_answer(result, failed=True),
                    "step_count": total_steps,
                    "completed_steps": zero_based_index,
                    "failed_step": zero_based_index,
                    "results": results,
                    "last_result": copy.deepcopy(result),
                    "error": copy.deepcopy(result.get("error")),
                    "execution_trace": self._merge_execution_traces(results),
                }
'''

NEW_FAILURE_RETURN = '''                aggregate_result = {
                    "ok": False,
                    "summary": "step execution failed",
                    "message": self._extract_step_message(result, failed=True),
                    "final_answer": self._extract_step_final_answer(result, failed=True),
                    "step_count": total_steps,
                    "completed_steps": zero_based_index,
                    "failed_step": zero_based_index,
                    "results": results,
                    "last_result": copy.deepcopy(result),
                    "error": copy.deepcopy(result.get("error")),
                    "execution_trace": self._merge_execution_traces(results),
                }
                return self._attach_adapter_payload(aggregate_result)
'''


OLD_SUCCESS_RETURN = '''        last_result = copy.deepcopy(results[-1]) if results else None
        return {
            "ok": True,
            "summary": "all steps executed",
            "message": self._extract_step_message(last_result, failed=False) if isinstance(last_result, dict) else "執行完成",
            "final_answer": self._extract_step_final_answer(last_result, failed=False) if isinstance(last_result, dict) else "執行完成",
            "step_count": total_steps,
            "completed_steps": total_steps,
            "failed_step": None,
            "results": results,
            "last_result": last_result,
            "error": None,
            "execution_trace": self._merge_execution_traces(results),
        }
'''

NEW_SUCCESS_RETURN = '''        last_result = copy.deepcopy(results[-1]) if results else None
        aggregate_result = {
            "ok": True,
            "summary": "all steps executed",
            "message": self._extract_step_message(last_result, failed=False) if isinstance(last_result, dict) else "執行完成",
            "final_answer": self._extract_step_final_answer(last_result, failed=False) if isinstance(last_result, dict) else "執行完成",
            "step_count": total_steps,
            "completed_steps": total_steps,
            "failed_step": None,
            "results": results,
            "last_result": last_result,
            "error": None,
            "execution_trace": self._merge_execution_traces(results),
        }
        return self._attach_adapter_payload(aggregate_result)
'''


OLD_ATTACH_METHOD = '''    def _attach_execution_trace(self, step: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        normalized = copy.deepcopy(result)
        normalized["runtime_mode"] = self._normalize_runtime_mode(
            normalized.get("runtime_mode")
            or (step.get("runtime_mode") if isinstance(step, dict) else "")
            or "execute"
        )
        normalized["execution_trace"] = self._build_execution_trace(step, normalized)

        if isinstance(normalized.get("result"), dict):
            normalized["result"]["runtime_mode"] = normalized["runtime_mode"]
            normalized["result"]["execution_trace"] = copy.deepcopy(normalized["execution_trace"])

        try:
            from core.runtime.payload_normalizer import normalize_runtime_adapter_payload

            normalized["adapter_payload"] = normalize_runtime_adapter_payload(normalized)
        except Exception:
            normalized["adapter_payload"] = {
                "ok": normalized.get("ok"),
                "message": str(normalized.get("message") or ""),
                "final_answer": str(normalized.get("final_answer") or ""),
                "text": str(normalized.get("message") or normalized.get("final_answer") or ""),
                "error_text": "",
                "error_type": "",
                "runtime_mode": str(normalized.get("runtime_mode") or ""),
                "last_result": normalized.get("last_result") if isinstance(normalized.get("last_result"), dict) else None,
                "execution_trace": copy.deepcopy(normalized.get("execution_trace")) if isinstance(normalized.get("execution_trace"), list) else [],
                "raw": copy.deepcopy(normalized),
            }

        return normalized
'''

NEW_ATTACH_METHOD = '''    def _attach_adapter_payload(self, result: Dict[str, Any]) -> Dict[str, Any]:
        normalized = copy.deepcopy(result)

        try:
            from core.runtime.payload_normalizer import normalize_runtime_adapter_payload

            normalized["adapter_payload"] = normalize_runtime_adapter_payload(normalized)
        except Exception:
            normalized["adapter_payload"] = {
                "ok": normalized.get("ok"),
                "message": str(normalized.get("message") or ""),
                "final_answer": str(normalized.get("final_answer") or ""),
                "text": str(normalized.get("message") or normalized.get("final_answer") or ""),
                "error_text": "",
                "error_type": "",
                "runtime_mode": str(normalized.get("runtime_mode") or ""),
                "last_result": normalized.get("last_result") if isinstance(normalized.get("last_result"), dict) else None,
                "execution_trace": copy.deepcopy(normalized.get("execution_trace")) if isinstance(normalized.get("execution_trace"), list) else [],
                "raw": copy.deepcopy(normalized),
            }

        return normalized

    def _attach_execution_trace(self, step: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        normalized = copy.deepcopy(result)
        normalized["runtime_mode"] = self._normalize_runtime_mode(
            normalized.get("runtime_mode")
            or (step.get("runtime_mode") if isinstance(step, dict) else "")
            or "execute"
        )
        normalized["execution_trace"] = self._build_execution_trace(step, normalized)

        if isinstance(normalized.get("result"), dict):
            normalized["result"]["runtime_mode"] = normalized["runtime_mode"]
            normalized["result"]["execution_trace"] = copy.deepcopy(normalized["execution_trace"])

        return self._attach_adapter_payload(normalized)
'''


TEST_FILE = r'''from __future__ import annotations

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
                    {"type": "noop", "message": "should not run"},
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
            result = _execute_steps(executor, [{"type": "noop", "message": "done"}])

        adapter = result.get("adapter_payload")

        self.assertIsInstance(adapter, dict)
        self.assertIs(adapter.get("ok"), True)
        self.assertIsInstance(adapter.get("message"), str)
        self.assertIsInstance(adapter.get("final_answer"), str)
        self.assertIsInstance(adapter.get("execution_trace"), list)


if __name__ == "__main__":
    unittest.main()
'''


def _replace_once(text: str, old: str, new: str, label: str) -> tuple[str, bool]:
    if new in text:
        print(f"[runtime-aggregate-adapter-v1] {label} already applied")
        return text, True

    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 target block, found {count}")

    return text.replace(old, new, 1), False


def main() -> int:
    text = STEP_EXECUTOR_PATH.read_text(encoding="utf-8")

    text, _ = _replace_once(text, OLD_FAILURE_RETURN, NEW_FAILURE_RETURN, "failure aggregate return")
    text, _ = _replace_once(text, OLD_SUCCESS_RETURN, NEW_SUCCESS_RETURN, "success aggregate return")
    text, _ = _replace_once(text, OLD_ATTACH_METHOD, NEW_ATTACH_METHOD, "adapter attach helper")

    STEP_EXECUTOR_PATH.write_text(text, encoding="utf-8", newline="\n")
    print("[runtime-aggregate-adapter-v1] updated core/runtime/step_executor.py")

    if TEST_PATH.exists():
        print("[runtime-aggregate-adapter-v1] test already exists")
    else:
        TEST_PATH.write_text(TEST_FILE, encoding="utf-8", newline="\n")
        print("[runtime-aggregate-adapter-v1] created tests/test_step_executor_runtime_aggregate_adapter.py")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())