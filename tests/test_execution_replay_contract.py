from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ExecutionReplayContractTest(unittest.TestCase):
    def _operation(
        self,
        operation_id="op-1",
        operation="lifecycle.queue",
        metadata=None,
    ):
        from core.runtime.runtime_operation import RuntimeOperation

        return RuntimeOperation(
            operation_id,
            operation,
            runtime_args={"operation_arg": operation_id},
            metadata=metadata if metadata is not None else {"operation": operation},
        )

    def _graph(self, order=None, dependency=True):
        from core.runtime.runtime_execution_graph import RuntimeExecutionGraph

        graph = RuntimeExecutionGraph()
        for operation_id, operation in order or [
            ("op-2", "lifecycle.dispatch"),
            ("op-1", "lifecycle.queue"),
        ]:
            graph.add_node(operation_id, operation)
        if dependency:
            graph.add_dependency("op-1", "op-2")
        return graph

    def _transaction(self, operations=None):
        from core.runtime.runtime_transaction import RuntimeTransaction

        transaction = RuntimeTransaction("tx-1")
        for operation in operations or [
            self._operation("op-1", "lifecycle.queue"),
            self._operation("op-2", "lifecycle.dispatch"),
        ]:
            transaction.add_operation(operation)
        return transaction

    def _plan(
        self,
        plan_id="plan-1",
        graph=None,
        transaction=None,
        metadata=None,
        runtime_args=None,
    ):
        from core.runtime.execution_plan import ExecutionPlan

        return ExecutionPlan(
            plan_id,
            graph if graph is not None else self._graph(),
            transaction if transaction is not None else self._transaction(),
            runtime_args=runtime_args
            if runtime_args is not None
            else {"scope": {"name": "runtime"}},
            metadata=metadata
            if metadata is not None
            else {"source": {"name": "contract"}},
        )

    def _snapshot(self, plan=None, snapshot_id="snapshot-1"):
        from core.runtime.execution_plan_snapshot import ExecutionPlanSnapshot

        return ExecutionPlanSnapshot.from_plan(
            snapshot_id,
            plan if plan is not None else self._plan(),
            created_at="time-a",
        )

    def _verifier(self, replay_id="replay-1"):
        from core.runtime.execution_replay import ExecutionReplayVerifier

        return ExecutionReplayVerifier(replay_id)

    def _mismatch_types(self, record):
        return [mismatch["type"] for mismatch in record.mismatches]

    def test_replay_id_validation(self) -> None:
        from core.runtime.execution_replay import (
            ExecutionReplayRejected,
            ExecutionReplayVerifier,
        )

        with self.assertRaises(ExecutionReplayRejected):
            ExecutionReplayVerifier("")

    def test_verify_snapshot_success_record(self) -> None:
        snapshot = self._snapshot()
        record = self._verifier().verify_snapshot(snapshot)

        self.assertEqual(record.replay_id, "replay-1")
        self.assertEqual(record.snapshot_id, "snapshot-1")
        self.assertEqual(record.plan_id, "plan-1")
        self.assertEqual(record.snapshot_fingerprint, snapshot.fingerprint)
        self.assertEqual(record.plan_fingerprint, snapshot.plan_fingerprint)
        self.assertEqual(record.replay_execution_order, ["op-1", "op-2"])
        self.assertEqual(record.operation_fingerprints, snapshot.operation_fingerprints)
        self.assertEqual(record.aggregate_status, "pending")
        self.assertEqual(record.verification_result, "verified")
        self.assertEqual(record.mismatches, [])

    def test_verify_plan_against_snapshot_success(self) -> None:
        plan = self._plan()
        snapshot = self._snapshot(plan=plan)
        record = self._verifier().verify_plan_against_snapshot(plan, snapshot)

        self.assertEqual(record.verification_result, "verified")
        self.assertEqual(record.mismatches, [])

    def test_plan_id_mismatch_detection(self) -> None:
        snapshot = self._snapshot()
        plan = self._plan(plan_id="plan-2")
        record = self._verifier().verify_plan_against_snapshot(plan, snapshot)

        self.assertIn("plan_id_mismatch", self._mismatch_types(record))
        self.assertEqual(record.verification_result, "mismatched")

    def test_plan_fingerprint_mismatch_detection(self) -> None:
        snapshot = self._snapshot()
        plan = self._plan(metadata={"source": {"name": "changed"}})
        record = self._verifier().verify_plan_against_snapshot(plan, snapshot)

        self.assertIn("plan_fingerprint_mismatch", self._mismatch_types(record))

    def test_execution_order_mismatch_detection(self) -> None:
        snapshot = self._snapshot()
        graph = self._graph(
            order=[
                ("op-2", "lifecycle.dispatch"),
                ("op-1", "lifecycle.queue"),
            ],
            dependency=False,
        )
        plan = self._plan(graph=graph)
        record = self._verifier().verify_plan_against_snapshot(plan, snapshot)

        self.assertIn("execution_order_mismatch", self._mismatch_types(record))

    def test_operation_fingerprint_mismatch_detection(self) -> None:
        snapshot = self._snapshot()
        transaction = self._transaction(
            [
                self._operation(
                    "op-1",
                    "lifecycle.queue",
                    metadata={"operation": "changed"},
                ),
                self._operation("op-2", "lifecycle.dispatch"),
            ]
        )
        plan = self._plan(transaction=transaction)
        record = self._verifier().verify_plan_against_snapshot(plan, snapshot)

        self.assertIn(
            "operation_fingerprint_mismatch",
            self._mismatch_types(record),
        )

    def test_missing_operation_detection(self) -> None:
        snapshot = self._snapshot()
        graph = self._graph(order=[("op-1", "lifecycle.queue")], dependency=False)
        plan = self._plan(
            graph=graph,
            transaction=self._transaction(
                [self._operation("op-1", "lifecycle.queue")]
            ),
        )
        record = self._verifier().verify_plan_against_snapshot(plan, snapshot)

        self.assertIn("missing_operation", self._mismatch_types(record))

    def test_extra_operation_detection(self) -> None:
        snapshot = self._snapshot()
        graph = self._graph(
            order=[
                ("op-2", "lifecycle.dispatch"),
                ("op-1", "lifecycle.queue"),
                ("op-3", "recovery.run"),
            ]
        )
        graph.add_dependency("op-2", "op-3")
        plan = self._plan(
            graph=graph,
            transaction=self._transaction(
                [
                    self._operation("op-1", "lifecycle.queue"),
                    self._operation("op-2", "lifecycle.dispatch"),
                    self._operation("op-3", "recovery.run"),
                ]
            ),
        )
        record = self._verifier().verify_plan_against_snapshot(plan, snapshot)

        self.assertIn("extra_operation", self._mismatch_types(record))

    def test_aggregate_status_mismatch_detection(self) -> None:
        snapshot = self._snapshot()
        transaction = self._transaction()
        transaction.get_operation("op-1").start().succeed()
        transaction.get_operation("op-2").start().succeed()
        plan = self._plan(transaction=transaction)
        record = self._verifier().verify_plan_against_snapshot(plan, snapshot)

        self.assertIn("aggregate_status_mismatch", self._mismatch_types(record))

    def test_replay_fingerprint_deterministic(self) -> None:
        snapshot = self._snapshot()
        first = self._verifier().verify_snapshot(snapshot)
        second = self._verifier().verify_snapshot(snapshot)

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_replay_fingerprint_changes_when_mismatch_changes(self) -> None:
        snapshot = self._snapshot()
        metadata_mismatch = self._verifier().verify_plan_against_snapshot(
            self._plan(metadata={"source": {"name": "changed"}}),
            snapshot,
        )
        status_mismatch = self._verifier().verify_plan_against_snapshot(
            self._succeeded_plan(),
            snapshot,
        )

        self.assertNotEqual(metadata_mismatch.fingerprint, status_mismatch.fingerprint)

    def test_copy_on_read_immutable_behavior(self) -> None:
        snapshot = self._snapshot()
        record = self._verifier().verify_snapshot(snapshot)
        execution_order = record.replay_execution_order
        operation_fingerprints = record.operation_fingerprints
        mismatches = record.mismatches

        execution_order.append("polluted")
        operation_fingerprints["op-1"] = "polluted"
        mismatches.append({"type": "polluted"})

        self.assertEqual(record.replay_execution_order, ["op-1", "op-2"])
        self.assertNotEqual(record.operation_fingerprints["op-1"], "polluted")
        self.assertEqual(record.mismatches, [])

    def _succeeded_plan(self):
        transaction = self._transaction()
        transaction.get_operation("op-1").start().succeed()
        transaction.get_operation("op-2").start().succeed()
        return self._plan(transaction=transaction)


if __name__ == "__main__":
    unittest.main()
