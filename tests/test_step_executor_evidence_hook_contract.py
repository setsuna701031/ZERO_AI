from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class StepExecutorEvidenceHookContractTest(unittest.TestCase):
    def _hook(self, hook_id="hook-1"):
        from core.runtime.step_executor_evidence_hook import StepExecutorEvidenceHook

        return StepExecutorEvidenceHook(hook_id)

    def test_hook_id_validation(self) -> None:
        from core.runtime.step_executor_evidence_hook import (
            StepExecutorEvidenceHook,
            StepExecutorEvidenceHookRejected,
        )

        with self.assertRaises(StepExecutorEvidenceHookRejected):
            StepExecutorEvidenceHook("")

    def test_before_step_event_success(self) -> None:
        event = self._hook().before_step(
            "task-1",
            "step-1",
            "command",
            metadata={"source": "contract"},
            runtime_args={"mode": "dry"},
        )

        self.assertEqual(event.phase, "before_step")
        self.assertEqual(event.status, "pending")
        self.assertEqual(event.task_id, "task-1")
        self.assertEqual(event.metadata, {"source": "contract"})
        self.assertEqual(event.runtime_args, {"mode": "dry"})

    def test_after_step_event_success(self) -> None:
        event = self._hook().after_step(
            "task-1",
            "step-1",
            "command",
            "succeeded",
            evidence_refs={"bundle_id": "bundle-1"},
        )

        self.assertEqual(event.phase, "after_step")
        self.assertEqual(event.status, "succeeded")
        self.assertEqual(event.evidence_refs, {"bundle_id": "bundle-1"})

    def test_failure_event_success(self) -> None:
        event = self._hook().on_step_failure(
            "task-1",
            "step-1",
            "command",
            {"error": "boom"},
            evidence_refs={"snapshot_id": "snapshot-1"},
        )

        self.assertEqual(event.phase, "step_failure")
        self.assertEqual(event.status, "failed")
        self.assertEqual(event.error, {"error": "boom"})
        self.assertEqual(event.evidence_refs, {"snapshot_id": "snapshot-1"})

    def test_blocked_event_success(self) -> None:
        event = self._hook().on_step_blocked(
            "task-1",
            "step-1",
            "command",
            {"reason": "policy"},
            evidence_refs={"audit_id": "audit-1"},
        )

        self.assertEqual(event.phase, "step_blocked")
        self.assertEqual(event.status, "blocked")
        self.assertEqual(event.reason, {"reason": "policy"})
        self.assertEqual(event.evidence_refs, {"audit_id": "audit-1"})

    def test_deterministic_event_id_sequence(self) -> None:
        hook = self._hook()
        first = hook.before_step("task-1", "step-1", "command")
        second = hook.after_step("task-1", "step-1", "command", "succeeded")

        self.assertEqual(
            first.event_id,
            "hook-1:before_step:task-1:step-1:command:1",
        )
        self.assertEqual(
            second.event_id,
            "hook-1:after_step:task-1:step-1:command:2",
        )

    def test_deterministic_event_fingerprint(self) -> None:
        first = self._hook().before_step(
            "task-1",
            "step-1",
            "command",
            metadata={"b": 2, "a": 1},
        )
        second = self._hook().before_step(
            "task-1",
            "step-1",
            "command",
            metadata={"a": 1, "b": 2},
        )

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_deterministic_hook_fingerprint(self) -> None:
        first = self._hook()
        second = self._hook()
        first.before_step("task-1", "step-1", "command")
        first.after_step("task-1", "step-1", "command", "succeeded")
        second.before_step("task-1", "step-1", "command")
        second.after_step("task-1", "step-1", "command", "succeeded")

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_created_at_does_not_affect_fingerprint(self) -> None:
        from core.runtime.step_executor_evidence_hook import StepExecutorEvidenceEvent

        first = StepExecutorEvidenceEvent(
            "event-1",
            "hook-1",
            "before_step",
            "task-1",
            "step-1",
            "command",
            status="pending",
            created_at="2026-05-13T00:00:00+00:00",
        )
        second = StepExecutorEvidenceEvent(
            "event-1",
            "hook-1",
            "before_step",
            "task-1",
            "step-1",
            "command",
            status="pending",
            created_at="2027-01-01T00:00:00+00:00",
        )

        self.assertNotEqual(first.created_at, second.created_at)
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_copy_on_read_immutable_behavior(self) -> None:
        event = self._hook().after_step(
            "task-1",
            "step-1",
            "command",
            "succeeded",
            evidence_refs={"refs": ["bundle-1"]},
            metadata={"source": {"name": "contract"}},
            runtime_args={"mode": {"name": "dry"}},
        )
        evidence_refs = event.evidence_refs
        metadata = event.metadata
        runtime_args = event.runtime_args

        evidence_refs["refs"].append("polluted")
        metadata["source"]["name"] = "polluted"
        runtime_args["mode"]["name"] = "polluted"

        self.assertEqual(event.evidence_refs, {"refs": ["bundle-1"]})
        self.assertEqual(event.metadata, {"source": {"name": "contract"}})
        self.assertEqual(event.runtime_args, {"mode": {"name": "dry"}})

    def test_list_events_immutable_behavior(self) -> None:
        hook = self._hook()
        hook.before_step("task-1", "step-1", "command")
        events = hook.list_events()
        events[0]._metadata = {"polluted": True}
        events.clear()

        current = hook.list_events()
        self.assertEqual(len(current), 1)
        self.assertIsNone(current[0].metadata)

    def test_hook_does_not_mutate_input_metadata_runtime_args_evidence_refs(self) -> None:
        hook = self._hook()
        metadata = {"items": [{"id": "meta"}]}
        runtime_args = {"items": [{"id": "runtime"}]}
        evidence_refs = {"items": [{"id": "evidence"}]}
        before = (
            {"items": [{"id": "meta"}]},
            {"items": [{"id": "runtime"}]},
            {"items": [{"id": "evidence"}]},
        )

        hook.after_step(
            "task-1",
            "step-1",
            "command",
            "succeeded",
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

        self.assertEqual((metadata, runtime_args, evidence_refs), before)


if __name__ == "__main__":
    unittest.main()
