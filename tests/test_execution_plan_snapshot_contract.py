from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ExecutionPlanSnapshotContractTest(unittest.TestCase):
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

    def _plan(self, metadata=None, runtime_args=None):
        from core.runtime.execution_plan import ExecutionPlan

        return ExecutionPlan(
            "plan-1",
            self._graph(),
            self._transaction(),
            runtime_args=runtime_args
            if runtime_args is not None
            else {"scope": {"name": "runtime"}},
            metadata=metadata
            if metadata is not None
            else {"source": {"name": "contract"}},
        )

    def _snapshot(self, snapshot_id="snapshot-1", plan=None, created_at="time-a"):
        from core.runtime.execution_plan_snapshot import ExecutionPlanSnapshot

        return ExecutionPlanSnapshot.from_plan(
            snapshot_id,
            plan if plan is not None else self._plan(),
            created_at=created_at,
        )

    def test_snapshot_id_validation(self) -> None:
        from core.runtime.execution_plan_snapshot import (
            ExecutionPlanSnapshot,
            ExecutionPlanSnapshotRejected,
        )

        with self.assertRaises(ExecutionPlanSnapshotRejected):
            ExecutionPlanSnapshot("", self._plan())

    def test_snapshot_captures_plan_identity_and_fingerprint(self) -> None:
        plan = self._plan()
        snapshot = self._snapshot(plan=plan)

        self.assertEqual(snapshot.snapshot_id, "snapshot-1")
        self.assertEqual(snapshot.plan_id, "plan-1")
        self.assertEqual(snapshot.plan_fingerprint, plan.fingerprint)

    def test_snapshot_captures_deterministic_execution_order(self) -> None:
        snapshot = self._snapshot()

        self.assertEqual(snapshot.execution_order, ["op-1", "op-2"])

    def test_snapshot_captures_operation_fingerprints(self) -> None:
        plan = self._plan()
        operations = plan.execution_order()
        snapshot = self._snapshot(plan=plan)

        self.assertEqual(
            snapshot.operation_fingerprints,
            {
                operation.operation_id: operation.fingerprint
                for operation in operations
            },
        )

    def test_snapshot_captures_aggregate_status(self) -> None:
        from core.runtime.execution_plan import ExecutionPlan

        transaction = self._transaction()
        transaction.get_operation("op-1").start().succeed()
        transaction.get_operation("op-2").start().fail({"error": "boom"})
        plan = ExecutionPlan("plan-1", self._graph(), transaction)
        snapshot = self._snapshot(plan=plan)

        self.assertEqual(snapshot.status, "partial_failed")

    def test_metadata_runtime_args_execution_order_operation_fingerprints_copy_on_read(
        self,
    ) -> None:
        snapshot = self._snapshot()
        metadata = snapshot.metadata
        runtime_args = snapshot.runtime_args
        execution_order = snapshot.execution_order
        operation_fingerprints = snapshot.operation_fingerprints

        metadata["source"]["name"] = "polluted"
        runtime_args["scope"]["name"] = "polluted"
        execution_order.append("polluted")
        operation_fingerprints["op-1"] = "polluted"

        self.assertEqual(snapshot.metadata, {"source": {"name": "contract"}})
        self.assertEqual(snapshot.runtime_args, {"scope": {"name": "runtime"}})
        self.assertEqual(snapshot.execution_order, ["op-1", "op-2"])
        self.assertNotEqual(snapshot.operation_fingerprints["op-1"], "polluted")

    def test_snapshot_identity_fields_are_read_only(self) -> None:
        snapshot = self._snapshot()

        with self.assertRaises(AttributeError):
            snapshot.snapshot_id = "polluted"
        with self.assertRaises(AttributeError):
            snapshot.plan_id = "polluted"
        with self.assertRaises(AttributeError):
            snapshot.status = "polluted"

    def test_snapshot_unaffected_by_later_plan_mutation(self) -> None:
        plan = self._plan()
        snapshot = self._snapshot(plan=plan)

        plan._metadata["source"]["name"] = "polluted"
        plan._runtime_args["scope"]["name"] = "polluted"
        plan._graph.add_node("op-3", "recovery.run")
        plan._transaction.add_operation(self._operation("op-3", "recovery.run"))

        self.assertEqual(snapshot.metadata, {"source": {"name": "contract"}})
        self.assertEqual(snapshot.runtime_args, {"scope": {"name": "runtime"}})
        self.assertEqual(snapshot.execution_order, ["op-1", "op-2"])
        self.assertEqual(set(snapshot.operation_fingerprints), {"op-1", "op-2"})

    def test_snapshot_fingerprint_deterministic(self) -> None:
        first = self._snapshot(
            plan=self._plan(
                runtime_args={"b": 2, "a": 1},
                metadata={"z": 3, "a": 1},
            )
        )
        second = self._snapshot(
            plan=self._plan(
                runtime_args={"a": 1, "b": 2},
                metadata={"a": 1, "z": 3},
            )
        )

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_snapshot_fingerprint_changes_when_payload_changes(self) -> None:
        base = self._snapshot()
        changed_snapshot_id = self._snapshot(snapshot_id="snapshot-2")
        changed_metadata = self._snapshot(
            plan=self._plan(metadata={"source": {"name": "changed"}})
        )

        self.assertNotEqual(base.fingerprint, changed_snapshot_id.fingerprint)
        self.assertNotEqual(base.fingerprint, changed_metadata.fingerprint)

    def test_created_at_does_not_affect_fingerprint(self) -> None:
        first = self._snapshot(created_at="2026-05-13T00:00:00+00:00")
        second = self._snapshot(created_at="2027-01-01T00:00:00+00:00")

        self.assertNotEqual(first.created_at, second.created_at)
        self.assertEqual(first.fingerprint, second.fingerprint)


if __name__ == "__main__":
    unittest.main()
