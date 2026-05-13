from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RollbackVerificationContractTest(unittest.TestCase):
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
        graph.add_node("op-3", "mutation.write")
        graph.add_node("op-1", "lifecycle.queue")
        graph.add_node("op-2", "lifecycle.dispatch")
        graph.add_dependency("op-1", "op-2")
        graph.add_dependency("op-2", "op-3")
        return graph

    def _transaction(self):
        from core.runtime.runtime_transaction import RuntimeTransaction

        transaction = RuntimeTransaction("tx-1")
        transaction.add_operation(self._operation("op-1", "lifecycle.queue"))
        transaction.add_operation(self._operation("op-2", "lifecycle.dispatch"))
        transaction.add_operation(self._operation("op-3", "mutation.write"))
        return transaction

    def _plan(self):
        from core.runtime.execution_plan import ExecutionPlan

        return ExecutionPlan(
            "plan-1",
            self._graph(),
            self._transaction(),
            runtime_args={"scope": {"name": "runtime"}},
            metadata={"source": {"name": "contract"}},
        )

    def _snapshot(self):
        from core.runtime.execution_plan_snapshot import ExecutionPlanSnapshot

        return ExecutionPlanSnapshot.from_plan(
            "snapshot-1",
            self._plan(),
            created_at="snapshot-time",
        )

    def _verifier(self, rollback_id="rollback-1"):
        from core.runtime.rollback_verification import RollbackVerificationVerifier

        return RollbackVerificationVerifier(rollback_id)

    def _mismatch_types(self, record):
        return [mismatch["type"] for mismatch in record.mismatches]

    def test_rollback_id_validation(self) -> None:
        from core.runtime.rollback_verification import (
            RollbackVerificationRejected,
            RollbackVerificationVerifier,
        )

        with self.assertRaises(RollbackVerificationRejected):
            RollbackVerificationVerifier("")
        with self.assertRaises(RollbackVerificationRejected):
            self._verifier().verify_order_against_snapshot(
                "",
                ["op-3", "op-2", "op-1"],
                self._snapshot(),
            )

    def test_verify_snapshot_rollback_success(self) -> None:
        snapshot = self._snapshot()
        record = self._verifier().verify_snapshot_rollback(snapshot)

        self.assertEqual(record.rollback_id, "rollback-1")
        self.assertEqual(record.snapshot_id, "snapshot-1")
        self.assertEqual(record.plan_id, "plan-1")
        self.assertEqual(record.execution_order, ["op-1", "op-2", "op-3"])
        self.assertEqual(record.rollback_order, ["op-3", "op-2", "op-1"])
        self.assertEqual(record.verification_result, "verified")
        self.assertEqual(record.mismatches, [])
        self.assertEqual(record.snapshot_fingerprint, snapshot.fingerprint)
        self.assertEqual(record.aggregate_status, snapshot.status)
        self.assertEqual(record.operation_fingerprints, snapshot.operation_fingerprints)
        self.assertEqual(record.metadata, snapshot.metadata)
        self.assertEqual(record.runtime_args, snapshot.runtime_args)

    def test_verify_order_against_snapshot_success(self) -> None:
        record = self._verifier().verify_order_against_snapshot(
            "rollback-2",
            ["op-3", "op-2", "op-1"],
            self._snapshot(),
        )

        self.assertEqual(record.rollback_id, "rollback-2")
        self.assertEqual(record.verification_result, "verified")
        self.assertEqual(record.mismatches, [])

    def test_rollback_order_mismatch_detection(self) -> None:
        record = self._verifier().verify_order_against_snapshot(
            "rollback-2",
            ["op-2", "op-3", "op-1"],
            self._snapshot(),
        )

        self.assertIn("rollback_order_mismatch", self._mismatch_types(record))
        self.assertEqual(record.verification_result, "mismatched")

    def test_missing_operation_detection(self) -> None:
        record = self._verifier().verify_order_against_snapshot(
            "rollback-2",
            ["op-3", "op-1"],
            self._snapshot(),
        )

        self.assertIn("missing_operation", self._mismatch_types(record))

    def test_extra_operation_detection(self) -> None:
        record = self._verifier().verify_order_against_snapshot(
            "rollback-2",
            ["op-3", "op-2", "op-1", "op-4"],
            self._snapshot(),
        )

        self.assertIn("extra_operation", self._mismatch_types(record))

    def test_duplicate_operation_detection(self) -> None:
        record = self._verifier().verify_order_against_snapshot(
            "rollback-2",
            ["op-3", "op-2", "op-2", "op-1"],
            self._snapshot(),
        )

        self.assertIn("duplicate_operation", self._mismatch_types(record))

    def test_copy_on_read_immutable_behavior(self) -> None:
        record = self._verifier().verify_order_against_snapshot(
            "rollback-2",
            ["op-3", "op-2", "op-1", "op-4"],
            self._snapshot(),
        )
        execution_order = record.execution_order
        rollback_order = record.rollback_order
        mismatches = record.mismatches
        operation_fingerprints = record.operation_fingerprints
        metadata = record.metadata
        runtime_args = record.runtime_args

        execution_order.append("polluted")
        rollback_order.append("polluted")
        mismatches.append({"type": "polluted"})
        operation_fingerprints["op-1"] = "polluted"
        metadata["source"]["name"] = "polluted"
        runtime_args["scope"]["name"] = "polluted"

        self.assertEqual(record.execution_order, ["op-1", "op-2", "op-3"])
        self.assertEqual(record.rollback_order, ["op-3", "op-2", "op-1", "op-4"])
        self.assertNotIn({"type": "polluted"}, record.mismatches)
        self.assertNotEqual(record.operation_fingerprints["op-1"], "polluted")
        self.assertEqual(record.metadata, {"source": {"name": "contract"}})
        self.assertEqual(record.runtime_args, {"scope": {"name": "runtime"}})

    def test_fingerprint_deterministic(self) -> None:
        snapshot = self._snapshot()
        first = self._verifier().verify_order_against_snapshot(
            "rollback-2",
            ["op-3", "op-2", "op-1"],
            snapshot,
        )
        second = self._verifier().verify_order_against_snapshot(
            "rollback-2",
            ["op-3", "op-2", "op-1"],
            snapshot,
        )

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_created_at_does_not_affect_fingerprint(self) -> None:
        snapshot = self._snapshot()
        first = self._verifier().verify_snapshot_rollback(
            snapshot,
            created_at="2026-05-13T00:00:00+00:00",
        )
        second = self._verifier().verify_snapshot_rollback(
            snapshot,
            created_at="2027-01-01T00:00:00+00:00",
        )

        self.assertNotEqual(first.created_at, second.created_at)
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_fingerprint_changes_when_mismatch_or_order_changes(self) -> None:
        snapshot = self._snapshot()
        missing = self._verifier().verify_order_against_snapshot(
            "rollback-2",
            ["op-3", "op-1"],
            snapshot,
        )
        extra = self._verifier().verify_order_against_snapshot(
            "rollback-2",
            ["op-3", "op-2", "op-1", "op-4"],
            snapshot,
        )

        self.assertNotEqual(missing.fingerprint, extra.fingerprint)


if __name__ == "__main__":
    unittest.main()
