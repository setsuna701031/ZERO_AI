from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ExecutionAuditContractTest(unittest.TestCase):
    def _operation(self, operation_id="op-1", operation="lifecycle.queue"):
        from core.runtime.runtime_operation import RuntimeOperation

        return RuntimeOperation(
            operation_id,
            operation,
            runtime_args={"operation_arg": operation_id},
            metadata={"operation": operation},
        )

    def _graph(self):
        from core.runtime.runtime_execution_graph import RuntimeExecutionGraph

        graph = RuntimeExecutionGraph()
        graph.add_node("op-2", "lifecycle.dispatch")
        graph.add_node("op-1", "lifecycle.queue")
        graph.add_dependency("op-1", "op-2")
        return graph

    def _transaction(self):
        from core.runtime.runtime_transaction import RuntimeTransaction

        transaction = RuntimeTransaction("tx-1")
        transaction.add_operation(self._operation("op-1", "lifecycle.queue"))
        transaction.add_operation(self._operation("op-2", "lifecycle.dispatch"))
        return transaction

    def _plan(self, metadata=None):
        from core.runtime.execution_plan import ExecutionPlan

        return ExecutionPlan(
            "plan-1",
            self._graph(),
            self._transaction(),
            runtime_args={"scope": {"name": "runtime"}},
            metadata=metadata
            if metadata is not None
            else {"source": {"name": "contract"}},
        )

    def _snapshot(self, plan=None):
        from core.runtime.execution_plan_snapshot import ExecutionPlanSnapshot

        return ExecutionPlanSnapshot.from_plan(
            "snapshot-1",
            plan if plan is not None else self._plan(),
            created_at="snapshot-time",
        )

    def _replay_record(self, replay_id="replay-1", mismatch=False):
        from core.runtime.execution_replay import ExecutionReplayVerifier

        snapshot = self._snapshot()
        verifier = ExecutionReplayVerifier(replay_id)
        if mismatch:
            plan = self._plan(metadata={"source": {"name": "changed"}})
            return verifier.verify_plan_against_snapshot(plan, snapshot)

        return verifier.verify_snapshot(snapshot)

    def _audit_record(
        self,
        audit_id="audit-1",
        replay_record=None,
        metadata=None,
        runtime_args=None,
        created_at="audit-time-a",
    ):
        from core.runtime.execution_audit import ExecutionAuditRecord

        return ExecutionAuditRecord.from_replay_record(
            audit_id,
            replay_record if replay_record is not None else self._replay_record(),
            metadata=metadata
            if metadata is not None
            else {"audit": {"source": "contract"}},
            runtime_args=runtime_args
            if runtime_args is not None
            else {"runtime": {"mode": "verify"}},
            created_at=created_at,
        )

    def test_audit_id_validation(self) -> None:
        from core.runtime.execution_audit import (
            ExecutionAuditRecord,
            ExecutionAuditRejected,
        )

        replay = self._replay_record()
        with self.assertRaises(ExecutionAuditRejected):
            ExecutionAuditRecord.from_replay_record("", replay)

    def test_audit_record_from_replay_record(self) -> None:
        replay = self._replay_record()
        audit = self._audit_record(replay_record=replay)

        self.assertEqual(audit.audit_id, "audit-1")
        self.assertEqual(audit.replay_id, replay.replay_id)
        self.assertEqual(audit.snapshot_id, replay.snapshot_id)
        self.assertEqual(audit.plan_id, replay.plan_id)
        self.assertEqual(audit.execution_order, replay.replay_execution_order)
        self.assertEqual(audit.operation_fingerprints, replay.operation_fingerprints)

    def test_audit_record_captures_replay_identity_result_mismatches(self) -> None:
        replay = self._replay_record(mismatch=True)
        audit = self._audit_record(replay_record=replay)

        self.assertEqual(audit.replay_id, "replay-1")
        self.assertEqual(audit.verification_result, "mismatched")
        self.assertEqual(audit.mismatches, replay.mismatches)
        self.assertEqual(audit.replay_fingerprint, replay.fingerprint)
        self.assertEqual(audit.aggregate_status, replay.aggregate_status)

    def test_copy_on_read_immutable_behavior(self) -> None:
        audit = self._audit_record(replay_record=self._replay_record(mismatch=True))
        mismatches = audit.mismatches
        metadata = audit.metadata
        runtime_args = audit.runtime_args
        execution_order = audit.execution_order
        operation_fingerprints = audit.operation_fingerprints

        mismatches.append({"type": "polluted"})
        metadata["audit"]["source"] = "polluted"
        runtime_args["runtime"]["mode"] = "polluted"
        execution_order.append("polluted")
        operation_fingerprints["op-1"] = "polluted"

        self.assertNotIn({"type": "polluted"}, audit.mismatches)
        self.assertEqual(audit.metadata, {"audit": {"source": "contract"}})
        self.assertEqual(audit.runtime_args, {"runtime": {"mode": "verify"}})
        self.assertEqual(audit.execution_order, ["op-1", "op-2"])
        self.assertNotEqual(audit.operation_fingerprints["op-1"], "polluted")

    def test_audit_fingerprint_deterministic(self) -> None:
        replay = self._replay_record()
        first = self._audit_record(
            replay_record=replay,
            metadata={"b": 2, "a": 1},
            runtime_args={"z": 3, "a": 1},
        )
        second = self._audit_record(
            replay_record=replay,
            metadata={"a": 1, "b": 2},
            runtime_args={"a": 1, "z": 3},
        )

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_created_at_does_not_affect_fingerprint(self) -> None:
        replay = self._replay_record()
        first = self._audit_record(
            replay_record=replay,
            created_at="2026-05-13T00:00:00+00:00",
        )
        second = self._audit_record(
            replay_record=replay,
            created_at="2027-01-01T00:00:00+00:00",
        )

        self.assertNotEqual(first.created_at, second.created_at)
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_trail_append_get_list_behavior(self) -> None:
        from core.runtime.execution_audit import ExecutionAuditTrail

        trail = ExecutionAuditTrail()
        first = self._audit_record("audit-1")
        second = self._audit_record("audit-2", self._replay_record("replay-2"))

        appended = trail.append_record(first)
        trail.append_record(second)

        self.assertEqual(appended.audit_id, "audit-1")
        self.assertEqual(trail.get_record("audit-1").audit_id, "audit-1")
        self.assertEqual(
            [record.audit_id for record in trail.list_records()],
            ["audit-1", "audit-2"],
        )

    def test_duplicate_audit_id_reject(self) -> None:
        from core.runtime.execution_audit import (
            ExecutionAuditRejected,
            ExecutionAuditTrail,
        )

        trail = ExecutionAuditTrail()
        trail.append_record(self._audit_record("audit-1"))

        with self.assertRaises(ExecutionAuditRejected):
            trail.append_record(self._audit_record("audit-1"))

    def test_trail_insertion_order_deterministic(self) -> None:
        from core.runtime.execution_audit import ExecutionAuditTrail

        trail = ExecutionAuditTrail()
        trail.append_record(self._audit_record("audit-2", self._replay_record("replay-2")))
        trail.append_record(self._audit_record("audit-1", self._replay_record("replay-1")))

        self.assertEqual(
            [record.audit_id for record in trail.list_records()],
            ["audit-2", "audit-1"],
        )

    def test_trail_fingerprint_deterministic(self) -> None:
        first = self._trail_with_two_records()
        second = self._trail_with_two_records()

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_trail_fingerprint_changes_when_record_added(self) -> None:
        trail = self._trail_with_two_records()
        before = trail.fingerprint
        trail.append_record(self._audit_record("audit-3", self._replay_record("replay-3")))

        self.assertNotEqual(before, trail.fingerprint)

    def test_list_records_returns_copy(self) -> None:
        trail = self._trail_with_two_records()
        records = trail.list_records()
        records[0]._metadata["audit"]["source"] = "polluted"
        records.clear()

        self.assertEqual(len(trail.list_records()), 2)
        self.assertEqual(
            trail.get_record("audit-1").metadata,
            {"audit": {"source": "contract"}},
        )

    def _trail_with_two_records(self):
        from core.runtime.execution_audit import ExecutionAuditTrail

        trail = ExecutionAuditTrail()
        trail.append_record(self._audit_record("audit-1", self._replay_record("replay-1")))
        trail.append_record(self._audit_record("audit-2", self._replay_record("replay-2")))
        return trail


if __name__ == "__main__":
    unittest.main()
