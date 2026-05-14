from __future__ import annotations

import copy
import inspect
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class FakeEvidenceAdapter:
    def __init__(self, fail=False) -> None:
        self.calls = []
        self.fail = fail

    def emit_before_step(self, **kwargs):
        self.calls.append(("before", copy.deepcopy(kwargs)))
        if self.fail:
            raise RuntimeError("adapter failed")

    def emit_after_step(self, **kwargs):
        self.calls.append(("after", copy.deepcopy(kwargs)))
        if self.fail:
            raise RuntimeError("adapter failed")

    def emit_failure(self, **kwargs):
        self.calls.append(("failure", copy.deepcopy(kwargs)))
        if self.fail:
            raise RuntimeError("adapter failed")

    def emit_blocked(self, **kwargs):
        self.calls.append(("blocked", copy.deepcopy(kwargs)))
        if self.fail:
            raise RuntimeError("adapter failed")


def _make_executor(workspace_root: Path, evidence_adapter=None) -> Any:
    from core.runtime.step_executor import StepExecutor

    signature = inspect.signature(StepExecutor)
    kwargs: Dict[str, Any] = {}
    if "workspace_root" in signature.parameters:
        kwargs["workspace_root"] = workspace_root
    if "runtime_store" in signature.parameters:
        kwargs["runtime_store"] = None
    if "tool_registry" in signature.parameters:
        kwargs["tool_registry"] = None
    if "llm_client" in signature.parameters:
        kwargs["llm_client"] = None
    if "debug" in signature.parameters:
        kwargs["debug"] = False
    kwargs["evidence_adapter"] = evidence_adapter

    return StepExecutor(**kwargs)


class StepExecutorHookAttachmentContractTest(unittest.TestCase):
    def test_no_adapter_existing_behavior_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = _make_executor(Path(tmp))
            result = executor.execute_step(
                {"id": "step-1", "type": "respond", "message": "done"},
                task={"task_id": "task-1"},
            )

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("step", {}).get("type"), "respond")
        self.assertFalse(hasattr(result, "evidence"))

    def test_adapter_before_step_called(self) -> None:
        adapter = FakeEvidenceAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            executor = _make_executor(Path(tmp), evidence_adapter=adapter)
            executor.execute_step(
                {"id": "step-1", "type": "respond", "message": "done"},
                task={"task_id": "task-1"},
            )

        self.assertEqual(adapter.calls[0][0], "before")
        self.assertEqual(adapter.calls[0][1]["task_id"], "task-1")
        self.assertEqual(adapter.calls[0][1]["step_id"], "step-1")
        self.assertEqual(adapter.calls[0][1]["step_type"], "respond")

    def test_success_result_triggers_after_step(self) -> None:
        adapter = FakeEvidenceAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            executor = _make_executor(Path(tmp), evidence_adapter=adapter)
            executor.execute_step(
                {"id": "step-1", "type": "respond", "message": "done"},
                task={"task_id": "task-1"},
            )

        self.assertEqual([call[0] for call in adapter.calls], ["before", "after"])
        self.assertTrue(adapter.calls[1][1]["step_result"].get("ok"))

    def test_failed_result_triggers_failure(self) -> None:
        adapter = FakeEvidenceAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            executor = _make_executor(Path(tmp), evidence_adapter=adapter)
            result = executor.execute_step(
                {"id": "step-1", "type": "not_real_step"},
                task={"task_id": "task-1"},
            )

        self.assertFalse(result.get("ok"))
        self.assertEqual([call[0] for call in adapter.calls], ["before", "failure"])

    def test_blocked_denied_result_triggers_blocked(self) -> None:
        adapter = FakeEvidenceAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            executor = _make_executor(Path(tmp), evidence_adapter=adapter)
            executor.register_handler(
                "blocked_probe",
                lambda step, task, context, previous: {
                    "ok": False,
                    "status": "blocked",
                    "reason": "denied",
                    "message": "blocked",
                },
            )
            result = executor.execute_step(
                {"id": "step-1", "type": "blocked_probe", "max_attempts": 1},
                task={"task_id": "task-1"},
            )

        self.assertFalse(result.get("ok"))
        self.assertEqual([call[0] for call in adapter.calls], ["before", "blocked"])

    def test_adapter_exception_does_not_change_step_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            baseline = _make_executor(Path(tmp)).execute_step(
                {"id": "step-1", "type": "respond", "message": "done"},
                task={"task_id": "task-1"},
            )
        with tempfile.TemporaryDirectory() as tmp:
            result = _make_executor(
                Path(tmp),
                evidence_adapter=FakeEvidenceAdapter(fail=True),
            ).execute_step(
                {"id": "step-1", "type": "respond", "message": "done"},
                task={"task_id": "task-1"},
            )

        self.assertEqual(result.get("ok"), baseline.get("ok"))
        self.assertEqual(result.get("message"), baseline.get("message"))
        self.assertEqual(result.get("final_answer"), baseline.get("final_answer"))
        self.assertEqual(result.get("error"), baseline.get("error"))

    def test_hook_event_order_deterministic(self) -> None:
        adapter = FakeEvidenceAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            executor = _make_executor(Path(tmp), evidence_adapter=adapter)
            executor.execute_step(
                {"id": "step-1", "type": "respond", "message": "done"},
                task={"task_id": "task-1"},
            )
            executor.execute_step(
                {"id": "step-2", "type": "not_real_step"},
                task={"task_id": "task-1"},
            )

        self.assertEqual(
            [call[0] for call in adapter.calls],
            ["before", "after", "before", "failure"],
        )

    def test_step_executor_does_not_expose_evidence_internals(self) -> None:
        adapter = FakeEvidenceAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            result = _make_executor(Path(tmp), evidence_adapter=adapter).execute_step(
                {"id": "step-1", "type": "respond", "message": "done"},
                task={"task_id": "task-1"},
            )

        self.assertNotIn("evidence", result)
        self.assertNotIn("evidence_adapter", result)
        self.assertNotIn("evidence_events", result)


if __name__ == "__main__":
    unittest.main()
