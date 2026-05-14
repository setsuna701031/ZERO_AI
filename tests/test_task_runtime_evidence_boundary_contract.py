from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TaskRuntimeEvidenceBoundaryContractTest(unittest.TestCase):
    def _boundary(self, boundary_id="boundary-1"):
        from core.runtime.task_runtime_evidence_boundary import (
            TaskRuntimeEvidenceBoundary,
        )

        return TaskRuntimeEvidenceBoundary(boundary_id)

    def test_boundary_id_validation(self) -> None:
        from core.runtime.task_runtime_evidence_boundary import (
            TaskRuntimeEvidenceBoundary,
            TaskRuntimeEvidenceBoundaryRejected,
        )

        with self.assertRaises(TaskRuntimeEvidenceBoundaryRejected):
            TaskRuntimeEvidenceBoundary("")

    def test_created_event_success(self) -> None:
        event = self._boundary().on_task_created(
            "task-1",
            "created",
            evidence_refs={"bundle_id": "bundle-1"},
            metadata={"source": "contract"},
            runtime_args={"mode": "dry"},
        )

        self.assertEqual(event.phase, "task_created")
        self.assertEqual(event.task_id, "task-1")
        self.assertEqual(event.runtime_status, "created")
        self.assertEqual(event.evidence_refs, {"bundle_id": "bundle-1"})
        self.assertEqual(event.metadata, {"source": "contract"})
        self.assertEqual(event.runtime_args, {"mode": "dry"})
        self.assertIsNone(event.error)
        self.assertIsNone(event.reason)
        self.assertEqual(event.sequence, 1)
        self.assertTrue(event.created_at)

    def test_started_event_success(self) -> None:
        event = self._boundary().on_task_started("task-1", "running")

        self.assertEqual(event.phase, "task_started")
        self.assertEqual(event.runtime_status, "running")

    def test_completed_event_success(self) -> None:
        event = self._boundary().on_task_completed(
            "task-1",
            "completed",
            evidence_refs={"audit_id": "audit-1"},
        )

        self.assertEqual(event.phase, "task_completed")
        self.assertEqual(event.runtime_status, "completed")
        self.assertEqual(event.evidence_refs, {"audit_id": "audit-1"})

    def test_failed_event_success(self) -> None:
        event = self._boundary().on_task_failed(
            "task-1",
            "failed",
            {"message": "boom"},
            evidence_refs={"snapshot_id": "snapshot-1"},
        )

        self.assertEqual(event.phase, "task_failed")
        self.assertEqual(event.runtime_status, "failed")
        self.assertEqual(event.error, {"message": "boom"})
        self.assertEqual(event.evidence_refs, {"snapshot_id": "snapshot-1"})
        self.assertIsNone(event.reason)

    def test_blocked_event_success(self) -> None:
        event = self._boundary().on_task_blocked(
            "task-1",
            "blocked",
            {"type": "policy"},
            evidence_refs={"replay_id": "replay-1"},
        )

        self.assertEqual(event.phase, "task_blocked")
        self.assertEqual(event.runtime_status, "blocked")
        self.assertEqual(event.reason, {"type": "policy"})
        self.assertEqual(event.evidence_refs, {"replay_id": "replay-1"})
        self.assertIsNone(event.error)

    def test_deterministic_event_id_sequence(self) -> None:
        boundary = self._boundary()
        created = boundary.on_task_created("task-1", "created")
        started = boundary.on_task_started("task-1", "running")
        completed = boundary.on_task_completed("task-1", "completed")

        self.assertEqual(
            created.event_id,
            "boundary-1:task_created:task-1:created:1",
        )
        self.assertEqual(
            started.event_id,
            "boundary-1:task_started:task-1:running:2",
        )
        self.assertEqual(
            completed.event_id,
            "boundary-1:task_completed:task-1:completed:3",
        )
        self.assertEqual([event.sequence for event in boundary.list_events()], [1, 2, 3])

    def test_deterministic_event_fingerprint(self) -> None:
        first = self._boundary().on_task_created(
            "task-1",
            "created",
            metadata={"b": 2, "a": 1},
        )
        second = self._boundary().on_task_created(
            "task-1",
            "created",
            metadata={"a": 1, "b": 2},
        )

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_deterministic_boundary_fingerprint(self) -> None:
        first = self._boundary()
        second = self._boundary()
        first.on_task_created("task-1", "created")
        first.on_task_started("task-1", "running")
        first.on_task_completed("task-1", "completed")
        second.on_task_created("task-1", "created")
        second.on_task_started("task-1", "running")
        second.on_task_completed("task-1", "completed")

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_created_at_does_not_affect_fingerprint(self) -> None:
        from core.runtime.task_runtime_evidence_boundary import (
            TaskRuntimeEvidenceEvent,
        )

        first = TaskRuntimeEvidenceEvent(
            "event-1",
            "boundary-1",
            "task_created",
            "task-1",
            "created",
            1,
            created_at="2026-05-13T00:00:00+00:00",
        )
        second = TaskRuntimeEvidenceEvent(
            "event-1",
            "boundary-1",
            "task_created",
            "task-1",
            "created",
            1,
            created_at="2027-01-01T00:00:00+00:00",
        )

        self.assertNotEqual(first.created_at, second.created_at)
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_copy_on_read_immutable_behavior(self) -> None:
        event = self._boundary().on_task_completed(
            "task-1",
            "completed",
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
        boundary = self._boundary()
        boundary.on_task_created("task-1", "created")
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
        before = (
            {"items": [{"id": "meta"}]},
            {"items": [{"id": "runtime"}]},
            {"items": [{"id": "evidence"}]},
        )

        boundary.on_task_completed(
            "task-1",
            "completed",
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )
        event = boundary.list_events()[0]
        metadata["items"][0]["id"] = "polluted"
        runtime_args["items"][0]["id"] = "polluted"
        evidence_refs["items"][0]["id"] = "polluted"

        self.assertEqual(event.metadata, before[0])
        self.assertEqual(event.runtime_args, before[1])
        self.assertEqual(event.evidence_refs, before[2])


if __name__ == "__main__":
    unittest.main()
