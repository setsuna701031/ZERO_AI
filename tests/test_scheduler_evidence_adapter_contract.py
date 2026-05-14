from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class SchedulerEvidenceAdapterContractTest(unittest.TestCase):
    def _boundary(self, boundary_id="boundary-1"):
        from core.runtime.scheduler_evidence_boundary import SchedulerEvidenceBoundary

        return SchedulerEvidenceBoundary(boundary_id)

    def _adapter(self, adapter_id="adapter-1", boundary=None):
        from core.runtime.scheduler_evidence_adapter import SchedulerEvidenceAdapter

        return SchedulerEvidenceAdapter(
            adapter_id,
            boundary if boundary is not None else self._boundary(),
        )

    def test_adapter_id_validation(self) -> None:
        from core.runtime.scheduler_evidence_adapter import (
            SchedulerEvidenceAdapter,
            SchedulerEvidenceAdapterRejected,
        )

        with self.assertRaises(SchedulerEvidenceAdapterRejected):
            SchedulerEvidenceAdapter("", self._boundary())

    def test_requires_boundary_instance(self) -> None:
        from core.runtime.scheduler_evidence_adapter import (
            SchedulerEvidenceAdapter,
            SchedulerEvidenceAdapterRejected,
        )

        with self.assertRaises(SchedulerEvidenceAdapterRejected):
            SchedulerEvidenceAdapter("adapter-1", object())

    def test_enqueued_emission(self) -> None:
        boundary = self._boundary()
        event = self._adapter(boundary=boundary).emit_enqueued(
            "scheduler-1",
            "task-1",
            "default",
            evidence_refs={"bundle_id": "bundle-1"},
            metadata={"source": "contract"},
            runtime_args={"mode": "dry"},
        )

        self.assertEqual(event.orchestration_phase, "task_enqueued")
        self.assertEqual(event.scheduler_id, "scheduler-1")
        self.assertEqual(event.task_id, "task-1")
        self.assertEqual(event.queue_name, "default")
        self.assertEqual(event.evidence_refs, {"bundle_id": "bundle-1"})
        self.assertEqual(event.metadata, {"source": "contract"})
        self.assertEqual(event.runtime_args, {"mode": "dry"})
        self.assertEqual(boundary.list_events()[0].event_id, event.event_id)

    def test_dequeued_emission(self) -> None:
        event = self._adapter().emit_dequeued("scheduler-1", "task-1", "default")

        self.assertEqual(event.orchestration_phase, "task_dequeued")
        self.assertEqual(event.scheduler_id, "scheduler-1")
        self.assertEqual(event.task_id, "task-1")
        self.assertEqual(event.queue_name, "default")

    def test_dispatched_emission(self) -> None:
        event = self._adapter().emit_dispatched(
            "scheduler-1",
            "task-1",
            "running",
            evidence_refs={"audit_id": "audit-1"},
        )

        self.assertEqual(event.orchestration_phase, "task_dispatched")
        self.assertEqual(event.queue_name, "running")
        self.assertEqual(event.evidence_refs, {"audit_id": "audit-1"})

    def test_requeued_emission(self) -> None:
        event = self._adapter().emit_requeued(
            "scheduler-1",
            "task-1",
            "retry",
            {"type": "dependency"},
            evidence_refs={"snapshot_id": "snapshot-1"},
        )

        self.assertEqual(event.orchestration_phase, "task_requeued")
        self.assertEqual(event.queue_name, "retry")
        self.assertEqual(event.reason, {"type": "dependency"})
        self.assertEqual(event.evidence_refs, {"snapshot_id": "snapshot-1"})

    def test_cancelled_emission(self) -> None:
        event = self._adapter().emit_cancelled(
            "scheduler-1",
            "task-1",
            "default",
            {"type": "user_request"},
            evidence_refs={"replay_id": "replay-1"},
        )

        self.assertEqual(event.orchestration_phase, "task_cancelled")
        self.assertEqual(event.reason, {"type": "user_request"})
        self.assertEqual(event.evidence_refs, {"replay_id": "replay-1"})

    def test_adapter_does_not_mutate_metadata_runtime_args_evidence_refs(self) -> None:
        adapter = self._adapter()
        metadata = {"items": [{"id": "meta"}]}
        runtime_args = {"items": [{"id": "runtime"}]}
        evidence_refs = {"items": [{"id": "evidence"}]}
        before = (
            {"items": [{"id": "meta"}]},
            {"items": [{"id": "runtime"}]},
            {"items": [{"id": "evidence"}]},
        )

        adapter.emit_dispatched(
            "scheduler-1",
            "task-1",
            "running",
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

        self.assertEqual((metadata, runtime_args, evidence_refs), before)

    def test_adapter_fingerprint_deterministic(self) -> None:
        first = self._adapter()
        second = self._adapter()
        first.emit_enqueued(
            "scheduler-1",
            "task-1",
            "default",
            metadata={"b": 2, "a": 1},
        )
        second.emit_enqueued(
            "scheduler-1",
            "task-1",
            "default",
            metadata={"a": 1, "b": 2},
        )

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_adapter_event_order_follows_boundary(self) -> None:
        boundary = self._boundary()
        adapter = self._adapter(boundary=boundary)
        adapter.emit_enqueued("scheduler-1", "task-1", "default")
        adapter.emit_dequeued("scheduler-1", "task-1", "default")
        adapter.emit_dispatched("scheduler-1", "task-1", "running")
        adapter.emit_requeued("scheduler-1", "task-1", "retry", {"type": "retry"})
        adapter.emit_cancelled("scheduler-1", "task-1", "default", {"type": "cancel"})

        self.assertEqual(
            [event.orchestration_phase for event in boundary.list_events()],
            [
                "task_enqueued",
                "task_dequeued",
                "task_dispatched",
                "task_requeued",
                "task_cancelled",
            ],
        )

    def test_created_at_does_not_affect_fingerprint(self) -> None:
        first = self._adapter()
        second = self._adapter()
        first.emit_dispatched("scheduler-1", "task-1", "running")
        second.emit_dispatched("scheduler-1", "task-1", "running")

        self.assertEqual(first.fingerprint, second.fingerprint)


if __name__ == "__main__":
    unittest.main()
