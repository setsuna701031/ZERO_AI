from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class StepExecutorEvidenceAdapterContractTest(unittest.TestCase):
    def _hook(self, hook_id="hook-1"):
        from core.runtime.step_executor_evidence_hook import StepExecutorEvidenceHook

        return StepExecutorEvidenceHook(hook_id)

    def _adapter(self, adapter_id="adapter-1", hook=None):
        from core.runtime.step_executor_evidence_adapter import (
            StepExecutorEvidenceAdapter,
        )

        return StepExecutorEvidenceAdapter(
            adapter_id,
            hook if hook is not None else self._hook(),
        )

    def test_adapter_id_validation(self) -> None:
        from core.runtime.step_executor_evidence_adapter import (
            StepExecutorEvidenceAdapter,
            StepExecutorEvidenceAdapterRejected,
        )

        with self.assertRaises(StepExecutorEvidenceAdapterRejected):
            StepExecutorEvidenceAdapter("", self._hook())

    def test_requires_hook_instance(self) -> None:
        from core.runtime.step_executor_evidence_adapter import (
            StepExecutorEvidenceAdapter,
            StepExecutorEvidenceAdapterRejected,
        )

        with self.assertRaises(StepExecutorEvidenceAdapterRejected):
            StepExecutorEvidenceAdapter("adapter-1", object())

    def test_before_step_emits_hook_event(self) -> None:
        hook = self._hook()
        event = self._adapter(hook=hook).emit_before_step(
            "task-1",
            "step-1",
            "command",
            metadata={"source": "contract"},
        )

        self.assertEqual(event.phase, "before_step")
        self.assertEqual(event.status, "pending")
        self.assertEqual(hook.list_events()[0].event_id, event.event_id)

    def test_after_step_status_normalization_success(self) -> None:
        adapter = self._adapter()

        self.assertEqual(
            adapter.emit_after_step("task-1", "step-1", "command", {"ok": True}).status,
            "succeeded",
        )
        self.assertEqual(
            adapter.emit_after_step(
                "task-1",
                "step-2",
                "command",
                {"status": "success"},
            ).status,
            "succeeded",
        )
        self.assertEqual(
            adapter.emit_after_step(
                "task-1",
                "step-3",
                "command",
                {"result": {"status": "succeeded"}},
            ).status,
            "succeeded",
        )

    def test_after_step_status_normalization_blocked(self) -> None:
        adapter = self._adapter()

        self.assertEqual(
            adapter.emit_after_step(
                "task-1",
                "step-1",
                "command",
                {"status": "blocked"},
            ).status,
            "blocked",
        )
        self.assertEqual(
            adapter.emit_after_step("task-1", "step-2", "command", "denied").status,
            "blocked",
        )

    def test_after_step_status_normalization_failed(self) -> None:
        adapter = self._adapter()

        for status in ("failed", "error", "exception"):
            self.assertEqual(
                adapter.emit_after_step(
                    "task-1",
                    f"step-{status}",
                    "command",
                    {"status": status},
                ).status,
                "failed",
            )

    def test_unknown_missing_status_becomes_failed(self) -> None:
        adapter = self._adapter()

        self.assertEqual(
            adapter.emit_after_step("task-1", "step-1", "command", {}).status,
            "failed",
        )
        self.assertEqual(
            adapter.emit_after_step(
                "task-1",
                "step-2",
                "command",
                {"status": "unknown"},
            ).status,
            "failed",
        )

    def test_failure_emission(self) -> None:
        event = self._adapter().emit_failure(
            "task-1",
            "step-1",
            "command",
            {"error": "boom"},
            evidence_refs={"bundle_id": "bundle-1"},
        )

        self.assertEqual(event.phase, "step_failure")
        self.assertEqual(event.status, "failed")
        self.assertEqual(event.error, {"error": "boom"})
        self.assertEqual(event.evidence_refs, {"bundle_id": "bundle-1"})

    def test_blocked_emission(self) -> None:
        event = self._adapter().emit_blocked(
            "task-1",
            "step-1",
            "command",
            {"reason": "policy"},
        )

        self.assertEqual(event.phase, "step_blocked")
        self.assertEqual(event.status, "blocked")
        self.assertEqual(event.reason, {"reason": "policy"})

    def test_adapter_does_not_mutate_inputs(self) -> None:
        adapter = self._adapter()
        step_result = {"result": {"status": "succeeded", "items": ["ok"]}}
        metadata = {"items": [{"id": "meta"}]}
        runtime_args = {"items": [{"id": "runtime"}]}
        evidence_refs = {"items": [{"id": "evidence"}]}
        before = (
            {"result": {"status": "succeeded", "items": ["ok"]}},
            {"items": [{"id": "meta"}]},
            {"items": [{"id": "runtime"}]},
            {"items": [{"id": "evidence"}]},
        )

        adapter.emit_after_step(
            "task-1",
            "step-1",
            "command",
            step_result,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

        self.assertEqual((step_result, metadata, runtime_args, evidence_refs), before)

    def test_adapter_fingerprint_deterministic(self) -> None:
        first = self._adapter()
        second = self._adapter()
        first.emit_before_step("task-1", "step-1", "command")
        second.emit_before_step("task-1", "step-1", "command")

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_adapter_event_order_follows_hook(self) -> None:
        hook = self._hook()
        adapter = self._adapter(hook=hook)
        adapter.emit_before_step("task-1", "step-1", "command")
        adapter.emit_after_step("task-1", "step-1", "command", {"ok": True})
        adapter.emit_failure("task-1", "step-2", "command", {"error": "boom"})

        self.assertEqual(
            [event.phase for event in hook.list_events()],
            ["before_step", "after_step", "step_failure"],
        )

    def test_created_at_does_not_affect_fingerprint(self) -> None:
        first = self._adapter()
        second = self._adapter()
        first.emit_after_step("task-1", "step-1", "command", {"ok": True})
        second.emit_after_step("task-1", "step-1", "command", {"ok": True})

        self.assertEqual(first.fingerprint, second.fingerprint)


if __name__ == "__main__":
    unittest.main()
