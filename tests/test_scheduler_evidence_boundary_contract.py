from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class SchedulerEvidenceBoundaryContractTest(unittest.TestCase):
    def _boundary(self, boundary_id="boundary-1"):
        from core.runtime.scheduler_evidence_boundary import SchedulerEvidenceBoundary

        return SchedulerEvidenceBoundary(boundary_id)

    def test_boundary_id_validation(self) -> None:
        from core.runtime.scheduler_evidence_boundary import (
            SchedulerEvidenceBoundary,
            SchedulerEvidenceBoundaryRejected,
        )

        with self.assertRaises(SchedulerEvidenceBoundaryRejected):
            SchedulerEvidenceBoundary("")

    def test_enqueued_event_success(self) -> None:
        event = self._boundary().on_task_enqueued(
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
        self.assertIsNone(event.reason)
        self.assertEqual(event.sequence, 1)
        self.assertTrue(event.created_at)

    def test_dequeued_event_success(self) -> None:
        event = self._boundary().on_task_dequeued("scheduler-1", "task-1", "default")

        self.assertEqual(event.orchestration_phase, "task_dequeued")
        self.assertEqual(event.scheduler_id, "scheduler-1")
        self.assertEqual(event.task_id, "task-1")
        self.assertEqual(event.queue_name, "default")

    def test_dispatched_event_success(self) -> None:
        event = self._boundary().on_task_dispatched(
            "scheduler-1",
            "task-1",
            "ready",
            evidence_refs={"audit_id": "audit-1"},
        )

        self.assertEqual(event.orchestration_phase, "task_dispatched")
        self.assertEqual(event.queue_name, "ready")
        self.assertEqual(event.evidence_refs, {"audit_id": "audit-1"})

    def test_requeued_event_success(self) -> None:
        event = self._boundary().on_task_requeued(
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

    def test_cancelled_event_success(self) -> None:
        event = self._boundary().on_task_cancelled(
            "scheduler-1",
            "task-1",
            "default",
            {"type": "user_request"},
            evidence_refs={"replay_id": "replay-1"},
        )

        self.assertEqual(event.orchestration_phase, "task_cancelled")
        self.assertEqual(event.reason, {"type": "user_request"})
        self.assertEqual(event.evidence_refs, {"replay_id": "replay-1"})

    def test_deterministic_event_id_sequence(self) -> None:
        boundary = self._boundary()
        enqueued = boundary.on_task_enqueued("scheduler-1", "task-1", "default")
        dequeued = boundary.on_task_dequeued("scheduler-1", "task-1", "default")
        dispatched = boundary.on_task_dispatched("scheduler-1", "task-1", "running")

        self.assertEqual(
            enqueued.event_id,
            "boundary-1:scheduler-1:task_enqueued:task-1:default:1",
        )
        self.assertEqual(
            dequeued.event_id,
            "boundary-1:scheduler-1:task_dequeued:task-1:default:2",
        )
        self.assertEqual(
            dispatched.event_id,
            "boundary-1:scheduler-1:task_dispatched:task-1:running:3",
        )
        self.assertEqual([event.sequence for event in boundary.list_events()], [1, 2, 3])

    def test_deterministic_event_fingerprint(self) -> None:
        first = self._boundary().on_task_enqueued(
            "scheduler-1",
            "task-1",
            "default",
            metadata={"b": 2, "a": 1},
        )
        second = self._boundary().on_task_enqueued(
            "scheduler-1",
            "task-1",
            "default",
            metadata={"a": 1, "b": 2},
        )

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_deterministic_boundary_fingerprint(self) -> None:
        first = self._boundary()
        second = self._boundary()
        first.on_task_enqueued("scheduler-1", "task-1", "default")
        first.on_task_dequeued("scheduler-1", "task-1", "default")
        first.on_task_dispatched("scheduler-1", "task-1", "running")
        second.on_task_enqueued("scheduler-1", "task-1", "default")
        second.on_task_dequeued("scheduler-1", "task-1", "default")
        second.on_task_dispatched("scheduler-1", "task-1", "running")

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_created_at_does_not_affect_fingerprint(self) -> None:
        from core.runtime.scheduler_evidence_boundary import SchedulerEvidenceEvent

        first = SchedulerEvidenceEvent(
            "event-1",
            "boundary-1",
            "scheduler-1",
            "task-1",
            "default",
            "task_enqueued",
            1,
            created_at="2026-05-13T00:00:00+00:00",
        )
        second = SchedulerEvidenceEvent(
            "event-1",
            "boundary-1",
            "scheduler-1",
            "task-1",
            "default",
            "task_enqueued",
            1,
            created_at="2027-01-01T00:00:00+00:00",
        )

        self.assertNotEqual(first.created_at, second.created_at)
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_copy_on_read_immutable_behavior(self) -> None:
        event = self._boundary().on_task_requeued(
            "scheduler-1",
            "task-1",
            "retry",
            {"items": ["reason-1"]},
            evidence_refs={"refs": ["bundle-1"]},
            metadata={"source": {"name": "contract"}},
            runtime_args={"mode": {"name": "dry"}},
        )
        reason = event.reason
        evidence_refs = event.evidence_refs
        metadata = event.metadata
        runtime_args = event.runtime_args

        reason["items"].append("polluted")
        evidence_refs["refs"].append("polluted")
        metadata["source"]["name"] = "polluted"
        runtime_args["mode"]["name"] = "polluted"

        self.assertEqual(event.reason, {"items": ["reason-1"]})
        self.assertEqual(event.evidence_refs, {"refs": ["bundle-1"]})
        self.assertEqual(event.metadata, {"source": {"name": "contract"}})
        self.assertEqual(event.runtime_args, {"mode": {"name": "dry"}})

    def test_list_events_immutable_behavior(self) -> None:
        boundary = self._boundary()
        boundary.on_task_enqueued("scheduler-1", "task-1", "default")
        events = boundary.list_events()
        events[0]._metadata = {"polluted": True}
        events.clear()

        current = boundary.list_events()
        self.assertEqual(len(current), 1)
        self.assertIsNone(current[0].metadata)

    def test_input_mutation_isolation(self) -> None:
        boundary = self._boundary()
        metadata = {"items": [{"id": "meta"}]}
        runtime_args = {"items": [{"id": "runtime"}]}
        evidence_refs = {"items": [{"id": "evidence"}]}
        reason = {"items": [{"id": "reason"}]}
        before = (
            {"items": [{"id": "meta"}]},
            {"items": [{"id": "runtime"}]},
            {"items": [{"id": "evidence"}]},
            {"items": [{"id": "reason"}]},
        )

        boundary.on_task_requeued(
            "scheduler-1",
            "task-1",
            "retry",
            reason,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )
        event = boundary.list_events()[0]
        metadata["items"][0]["id"] = "polluted"
        runtime_args["items"][0]["id"] = "polluted"
        evidence_refs["items"][0]["id"] = "polluted"
        reason["items"][0]["id"] = "polluted"

        self.assertEqual(event.metadata, before[0])
        self.assertEqual(event.runtime_args, before[1])
        self.assertEqual(event.evidence_refs, before[2])
        self.assertEqual(event.reason, before[3])


if __name__ == "__main__":
    unittest.main()
