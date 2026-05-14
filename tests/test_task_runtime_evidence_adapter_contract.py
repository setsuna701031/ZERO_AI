from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TaskRuntimeEvidenceAdapterContractTest(unittest.TestCase):
    def _boundary(self, boundary_id="boundary-1"):
        from core.runtime.task_runtime_evidence_boundary import (
            TaskRuntimeEvidenceBoundary,
        )

        return TaskRuntimeEvidenceBoundary(boundary_id)

    def _adapter(self, adapter_id="adapter-1", boundary=None):
        from core.runtime.task_runtime_evidence_adapter import (
            TaskRuntimeEvidenceAdapter,
        )

        return TaskRuntimeEvidenceAdapter(
            adapter_id,
            boundary if boundary is not None else self._boundary(),
        )

    def test_adapter_id_validation(self) -> None:
        from core.runtime.task_runtime_evidence_adapter import (
            TaskRuntimeEvidenceAdapter,
            TaskRuntimeEvidenceAdapterRejected,
        )

        with self.assertRaises(TaskRuntimeEvidenceAdapterRejected):
            TaskRuntimeEvidenceAdapter("", self._boundary())

    def test_requires_boundary_instance(self) -> None:
        from core.runtime.task_runtime_evidence_adapter import (
            TaskRuntimeEvidenceAdapter,
            TaskRuntimeEvidenceAdapterRejected,
        )

        with self.assertRaises(TaskRuntimeEvidenceAdapterRejected):
            TaskRuntimeEvidenceAdapter("adapter-1", object())

    def test_created_emission(self) -> None:
        boundary = self._boundary()
        event = self._adapter(boundary=boundary).emit_created(
            "task-1",
            "created",
            evidence_refs={"bundle_id": "bundle-1"},
            metadata={"source": "contract"},
            runtime_args={"mode": "dry"},
        )

        self.assertEqual(event.phase, "task_created")
        self.assertEqual(event.runtime_status, "created")
        self.assertEqual(event.evidence_refs, {"bundle_id": "bundle-1"})
        self.assertEqual(event.metadata, {"source": "contract"})
        self.assertEqual(event.runtime_args, {"mode": "dry"})
        self.assertEqual(boundary.list_events()[0].event_id, event.event_id)

    def test_started_emission(self) -> None:
        event = self._adapter().emit_started("task-1", "running")

        self.assertEqual(event.phase, "task_started")
        self.assertEqual(event.runtime_status, "running")

    def test_completed_emission(self) -> None:
        event = self._adapter().emit_completed(
            "task-1",
            "completed",
            evidence_refs={"audit_id": "audit-1"},
        )

        self.assertEqual(event.phase, "task_completed")
        self.assertEqual(event.runtime_status, "completed")
        self.assertEqual(event.evidence_refs, {"audit_id": "audit-1"})

    def test_failed_emission(self) -> None:
        event = self._adapter().emit_failed(
            "task-1",
            "failed",
            {"message": "boom"},
            evidence_refs={"snapshot_id": "snapshot-1"},
        )

        self.assertEqual(event.phase, "task_failed")
        self.assertEqual(event.runtime_status, "failed")
        self.assertEqual(event.error, {"message": "boom"})
        self.assertEqual(event.evidence_refs, {"snapshot_id": "snapshot-1"})

    def test_blocked_emission(self) -> None:
        event = self._adapter().emit_blocked(
            "task-1",
            "blocked",
            {"type": "policy"},
            evidence_refs={"replay_id": "replay-1"},
        )

        self.assertEqual(event.phase, "task_blocked")
        self.assertEqual(event.runtime_status, "blocked")
        self.assertEqual(event.reason, {"type": "policy"})
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

        adapter.emit_completed(
            "task-1",
            "completed",
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

        self.assertEqual((metadata, runtime_args, evidence_refs), before)

    def test_adapter_fingerprint_deterministic(self) -> None:
        first = self._adapter()
        second = self._adapter()
        first.emit_created("task-1", "created", metadata={"b": 2, "a": 1})
        second.emit_created("task-1", "created", metadata={"a": 1, "b": 2})

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_adapter_event_order_follows_boundary(self) -> None:
        boundary = self._boundary()
        adapter = self._adapter(boundary=boundary)
        adapter.emit_created("task-1", "created")
        adapter.emit_started("task-1", "running")
        adapter.emit_completed("task-1", "completed")
        adapter.emit_failed("task-2", "failed", {"message": "boom"})
        adapter.emit_blocked("task-3", "blocked", {"type": "policy"})

        self.assertEqual(
            [event.phase for event in boundary.list_events()],
            [
                "task_created",
                "task_started",
                "task_completed",
                "task_failed",
                "task_blocked",
            ],
        )

    def test_created_at_does_not_affect_fingerprint(self) -> None:
        first = self._adapter()
        second = self._adapter()
        first.emit_completed("task-1", "completed")
        second.emit_completed("task-1", "completed")

        self.assertEqual(first.fingerprint, second.fingerprint)


if __name__ == "__main__":
    unittest.main()
