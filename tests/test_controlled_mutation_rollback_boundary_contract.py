from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ControlledMutationRollbackBoundaryContractTest(unittest.TestCase):
    def _boundary(self, boundary_id: str = "rollback-boundary"):
        from core.runtime.controlled_mutation_rollback_boundary import (
            ControlledMutationRollbackBoundary,
        )

        return ControlledMutationRollbackBoundary(boundary_id)

    def test_boundary_id_validation(self) -> None:
        from core.runtime.controlled_mutation_rollback_boundary import (
            ControlledMutationRollbackBoundary,
            ControlledMutationRollbackRejected,
        )

        with self.assertRaises(ControlledMutationRollbackRejected):
            ControlledMutationRollbackBoundary("")

    def test_rollback_id_validation(self) -> None:
        from core.runtime.controlled_mutation_rollback_boundary import (
            ControlledMutationRollbackRejected,
        )

        with self.assertRaises(ControlledMutationRollbackRejected):
            self._boundary().record_rollback_planned(
                "",
                "sandbox-1",
                "mutation-1",
            )

    def test_planned_record_success(self) -> None:
        record = self._boundary().record_rollback_planned(
            "rollback-1",
            "sandbox-1",
            "mutation-1",
            rollback_strategy={"type": "reverse_patch"},
            evidence_refs={"plan": "evidence-1"},
            metadata={"source": "contract"},
            runtime_args={"mode": "dry"},
        )

        self.assertEqual(record.rollback_phase, "planned")
        self.assertEqual(record.rollback_strategy, {"type": "reverse_patch"})
        self.assertEqual(record.evidence_refs, {"plan": "evidence-1"})
        self.assertEqual(record.metadata, {"source": "contract"})
        self.assertEqual(record.runtime_args, {"mode": "dry"})

    def test_started_record_success(self) -> None:
        record = self._boundary().record_rollback_started(
            "rollback-1",
            "sandbox-1",
            "mutation-1",
            rollback_summary={"status": "started"},
        )

        self.assertEqual(record.rollback_phase, "started")
        self.assertEqual(record.rollback_summary, {"status": "started"})

    def test_completed_record_success(self) -> None:
        record = self._boundary().record_rollback_completed(
            "rollback-1",
            "sandbox-1",
            "mutation-1",
            {"ok": True, "restored": 2},
            evidence_refs={"rollback": "evidence-2"},
        )

        self.assertEqual(record.rollback_phase, "completed")
        self.assertEqual(record.rollback_summary, {"ok": True, "restored": 2})
        self.assertEqual(record.evidence_refs, {"rollback": "evidence-2"})

    def test_failed_record_success(self) -> None:
        record = self._boundary().record_rollback_failed(
            "rollback-1",
            "sandbox-1",
            "mutation-1",
            {"ok": False, "error": "restore failed"},
        )

        self.assertEqual(record.rollback_phase, "failed")
        self.assertEqual(record.rollback_summary, {"ok": False, "error": "restore failed"})

    def test_blocked_record_success(self) -> None:
        record = self._boundary().record_rollback_blocked(
            "rollback-1",
            "sandbox-1",
            "mutation-1",
            {"reason": "policy"},
            metadata={"blocked": True},
        )

        self.assertEqual(record.rollback_phase, "blocked")
        self.assertEqual(record.rollback_summary, {"reason": "policy"})
        self.assertEqual(record.metadata, {"blocked": True})

    def test_deterministic_record_id_sequence(self) -> None:
        boundary = self._boundary()
        boundary.record_rollback_planned("rollback-1", "sandbox-1", "mutation-1")
        boundary.record_rollback_started("rollback-1", "sandbox-1", "mutation-1")
        boundary.record_rollback_completed(
            "rollback-1",
            "sandbox-1",
            "mutation-1",
            {"ok": True},
        )
        boundary.record_rollback_failed(
            "rollback-2",
            "sandbox-1",
            "mutation-1",
            {"ok": False},
        )
        boundary.record_rollback_blocked(
            "rollback-3",
            "sandbox-1",
            "mutation-2",
            {"reason": "policy"},
        )

        self.assertEqual(
            [record.record_id for record in boundary.list_records()],
            [
                "rollback-boundary:rollback-1:sandbox-1:mutation-1:planned:1",
                "rollback-boundary:rollback-1:sandbox-1:mutation-1:started:2",
                "rollback-boundary:rollback-1:sandbox-1:mutation-1:completed:3",
                "rollback-boundary:rollback-2:sandbox-1:mutation-1:failed:4",
                "rollback-boundary:rollback-3:sandbox-1:mutation-2:blocked:5",
            ],
        )
        self.assertEqual(
            [record.sequence for record in boundary.list_records()],
            [1, 2, 3, 4, 5],
        )

    def test_deterministic_record_fingerprint(self) -> None:
        from core.runtime.controlled_mutation_rollback_boundary import (
            ControlledMutationRollbackRecord,
        )

        first = ControlledMutationRollbackRecord(
            "record-1",
            "boundary-1",
            "rollback-1",
            "sandbox-1",
            "mutation-1",
            "planned",
            1,
            rollback_strategy={"b": 2, "a": 1},
        )
        second = ControlledMutationRollbackRecord(
            "record-1",
            "boundary-1",
            "rollback-1",
            "sandbox-1",
            "mutation-1",
            "planned",
            1,
            rollback_strategy={"a": 1, "b": 2},
        )

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_deterministic_boundary_fingerprint(self) -> None:
        first = self._boundary()
        second = self._boundary()
        first.record_rollback_planned(
            "rollback-1",
            "sandbox-1",
            "mutation-1",
            metadata={"b": 2, "a": 1},
        )
        first.record_rollback_completed(
            "rollback-1",
            "sandbox-1",
            "mutation-1",
            {"ok": True},
        )
        second.record_rollback_planned(
            "rollback-1",
            "sandbox-1",
            "mutation-1",
            metadata={"a": 1, "b": 2},
        )
        second.record_rollback_completed(
            "rollback-1",
            "sandbox-1",
            "mutation-1",
            {"ok": True},
        )

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_created_at_does_not_affect_fingerprint(self) -> None:
        from core.runtime.controlled_mutation_rollback_boundary import (
            ControlledMutationRollbackRecord,
        )

        first = ControlledMutationRollbackRecord(
            "record-1",
            "boundary-1",
            "rollback-1",
            "sandbox-1",
            "mutation-1",
            "planned",
            1,
            created_at="2026-05-13T00:00:00+00:00",
        )
        second = ControlledMutationRollbackRecord(
            "record-1",
            "boundary-1",
            "rollback-1",
            "sandbox-1",
            "mutation-1",
            "planned",
            1,
            created_at="2027-01-01T00:00:00+00:00",
        )

        self.assertNotEqual(first.created_at, second.created_at)
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_copy_on_read_immutable_behavior(self) -> None:
        record = self._boundary().record_rollback_completed(
            "rollback-1",
            "sandbox-1",
            "mutation-1",
            {"items": [{"id": "summary"}]},
            rollback_strategy={"items": [{"id": "strategy"}]},
            evidence_refs={"items": [{"id": "evidence"}]},
            metadata={"items": [{"id": "metadata"}]},
            runtime_args={"items": [{"id": "runtime"}]},
        )
        rollback_strategy = record.rollback_strategy
        rollback_summary = record.rollback_summary
        evidence_refs = record.evidence_refs
        metadata = record.metadata
        runtime_args = record.runtime_args

        rollback_strategy["items"][0]["id"] = "polluted"
        rollback_summary["items"][0]["id"] = "polluted"
        evidence_refs["items"][0]["id"] = "polluted"
        metadata["items"][0]["id"] = "polluted"
        runtime_args["items"][0]["id"] = "polluted"

        self.assertEqual(record.rollback_strategy, {"items": [{"id": "strategy"}]})
        self.assertEqual(record.rollback_summary, {"items": [{"id": "summary"}]})
        self.assertEqual(record.evidence_refs, {"items": [{"id": "evidence"}]})
        self.assertEqual(record.metadata, {"items": [{"id": "metadata"}]})
        self.assertEqual(record.runtime_args, {"items": [{"id": "runtime"}]})

    def test_list_records_immutable_behavior(self) -> None:
        boundary = self._boundary()
        boundary.record_rollback_planned(
            "rollback-1",
            "sandbox-1",
            "mutation-1",
            metadata={"source": "contract"},
        )
        records = boundary.list_records()
        records[0]._metadata = {"polluted": True}
        records.clear()

        current = boundary.list_records()
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0].metadata, {"source": "contract"})

    def test_input_mutation_isolation(self) -> None:
        rollback_strategy = {"items": [{"id": "strategy"}]}
        rollback_summary = {"items": [{"id": "summary"}]}
        evidence_refs = {"items": [{"id": "evidence"}]}
        metadata = {"items": [{"id": "metadata"}]}
        runtime_args = {"items": [{"id": "runtime"}]}
        before = copy.deepcopy(
            (
                rollback_strategy,
                rollback_summary,
                evidence_refs,
                metadata,
                runtime_args,
            )
        )

        record = self._boundary().record_rollback_completed(
            "rollback-1",
            "sandbox-1",
            "mutation-1",
            rollback_summary,
            rollback_strategy=rollback_strategy,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )
        rollback_strategy["items"][0]["id"] = "polluted"
        rollback_summary["items"][0]["id"] = "polluted"
        evidence_refs["items"][0]["id"] = "polluted"
        metadata["items"][0]["id"] = "polluted"
        runtime_args["items"][0]["id"] = "polluted"

        self.assertEqual(
            (
                record.rollback_strategy,
                record.rollback_summary,
                record.evidence_refs,
                record.metadata,
                record.runtime_args,
            ),
            before,
        )

    def test_boundary_is_record_only_and_does_not_attach_runtime_executors(self) -> None:
        boundary = self._boundary()

        boundary.record_rollback_started(
            "rollback-1",
            "sandbox-1",
            "mutation-1",
            runtime_args={"revert": "planned-only"},
        )

        self.assertFalse(hasattr(boundary, "scheduler"))
        self.assertFalse(hasattr(boundary, "agent_loop"))
        self.assertFalse(hasattr(boundary, "step_executor"))
        self.assertFalse(hasattr(boundary, "persistence_backend"))


if __name__ == "__main__":
    unittest.main()
