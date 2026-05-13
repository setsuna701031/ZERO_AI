from __future__ import annotations

from pathlib import Path


STEP_EXECUTOR_PATH = Path("core/runtime/step_executor.py")
TEST_PATH = Path("tests/test_step_executor_runtime_event_integration_contract.py")


IMPORT_OLD = "from typing import Any, Callable, Dict, List, Optional\n"
IMPORT_NEW = """from typing import Any, Callable, Dict, List, Optional

from core.runtime.event_stream import attach_runtime_event_stream
"""


OLD_FAILED_RETURN = "                return self._attach_adapter_payload(aggregate_result)\n"
NEW_FAILED_RETURN = """                aggregate_result = self._attach_adapter_payload(aggregate_result)
                attach_runtime_event_stream(aggregate_result, source="step_executor")
                return aggregate_result
"""


OLD_SUCCESS_RETURN = "        return self._attach_adapter_payload(aggregate_result)\n"
NEW_SUCCESS_RETURN = """        aggregate_result = self._attach_adapter_payload(aggregate_result)
        attach_runtime_event_stream(aggregate_result, source="step_executor")
        return aggregate_result
"""


TEST_CONTENT = r'''from __future__ import annotations

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
'''


def main() -> None:
    if not STEP_EXECUTOR_PATH.exists():
        raise FileNotFoundError(STEP_EXECUTOR_PATH)

    source = STEP_EXECUTOR_PATH.read_text(encoding="utf-8")

    if "from core.runtime.event_stream import attach_runtime_event_stream" not in source:
        if IMPORT_OLD not in source:
            raise RuntimeError("step_executor import marker not found")
        source = source.replace(IMPORT_OLD, IMPORT_NEW, 1)

    if 'attach_runtime_event_stream(aggregate_result, source="step_executor")' not in source:
        if OLD_FAILED_RETURN not in source:
            raise RuntimeError("failed aggregate return marker not found")
        source = source.replace(OLD_FAILED_RETURN, NEW_FAILED_RETURN, 1)

        if OLD_SUCCESS_RETURN not in source:
            raise RuntimeError("success aggregate return marker not found")
        source = source.replace(OLD_SUCCESS_RETURN, NEW_SUCCESS_RETURN, 1)

    STEP_EXECUTOR_PATH.write_text(source, encoding="utf-8")
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")

    print("[runtime-step-executor-integration-v1] updated core/runtime/step_executor.py")
    print("[runtime-step-executor-integration-v1] created tests/test_step_executor_runtime_event_integration_contract.py")


if __name__ == "__main__":
    main()