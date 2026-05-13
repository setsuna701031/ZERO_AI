from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ExecutionPlanContractTest(unittest.TestCase):
    def _operation(self, operation_id="op-1", operation="lifecycle.queue"):
        from core.runtime.runtime_operation import RuntimeOperation

        return RuntimeOperation(operation_id, operation)

    def _graph(self):
        from core.runtime.runtime_execution_graph import RuntimeExecutionGraph

        graph = RuntimeExecutionGraph()
        graph.add_node("op-1", "lifecycle.queue")
        graph.add_node("op-2", "lifecycle.dispatch")
        graph.add_dependency("op-1", "op-2")
        return graph

    def _transaction(self):
        from core.runtime.runtime_transaction import RuntimeTransaction

        transaction = RuntimeTransaction("tx-1")
        transaction.add_operation(self._operation("op-1", "lifecycle.queue"))
        transaction.add_operation(self._operation("op-2", "lifecycle.dispatch"))
        return transaction

    def _plan(self):
        from core.runtime.execution_plan import ExecutionPlan

        return ExecutionPlan(
            "plan-1",
            self._graph(),
            self._transaction(),
            runtime_args={"scope": "runtime"},
            metadata={"source": "contract"},
        )

    def test_plan_id_validation(self) -> None:
        from core.runtime.execution_plan import ExecutionPlan, ExecutionPlanRejected

        with self.assertRaises(ExecutionPlanRejected):
            ExecutionPlan("", self._graph(), self._transaction())

    def test_graph_node_missing_operation_rejected(self) -> None:
        from core.runtime.execution_plan import ExecutionPlan, ExecutionPlanRejected
        from core.runtime.runtime_transaction import RuntimeTransaction

        transaction = RuntimeTransaction("tx-1")
        transaction.add_operation(self._operation("op-1", "lifecycle.queue"))

        with self.assertRaises(ExecutionPlanRejected):
            ExecutionPlan("plan-1", self._graph(), transaction)

    def test_transaction_operation_missing_graph_node_rejected(self) -> None:
        from core.runtime.execution_plan import ExecutionPlan, ExecutionPlanRejected

        transaction = self._transaction()
        transaction.add_operation(self._operation("op-3", "recovery.run"))

        with self.assertRaises(ExecutionPlanRejected):
            ExecutionPlan("plan-1", self._graph(), transaction)

    def test_graph_operation_name_mismatch_rejected(self) -> None:
        from core.runtime.execution_plan import ExecutionPlan, ExecutionPlanRejected
        from core.runtime.runtime_execution_graph import RuntimeExecutionGraph

        graph = RuntimeExecutionGraph()
        graph.add_node("op-1", "recovery.run")
        graph.add_node("op-2", "lifecycle.dispatch")
        graph.add_dependency("op-1", "op-2")

        with self.assertRaises(ExecutionPlanRejected):
            ExecutionPlan("plan-1", graph, self._transaction())

    def test_execution_order_deterministic(self) -> None:
        plan = self._plan()

        self.assertEqual(
            [operation.operation_id for operation in plan.execution_order()],
            ["op-1", "op-2"],
        )

    def test_execution_order_returns_operation_copy_and_list_copy(self) -> None:
        plan = self._plan()
        operations = plan.execution_order()
        operations[0].start().succeed()
        operations.clear()

        current = plan.execution_order()
        self.assertEqual(len(current), 2)
        self.assertEqual(current[0].status, "pending")

    def test_metadata_runtime_args_immutable_copy(self) -> None:
        plan = self._plan()
        metadata = plan.metadata
        runtime_args = plan.runtime_args
        metadata["source"] = "polluted"
        runtime_args["scope"] = "polluted"

        self.assertEqual(plan.metadata, {"source": "contract"})
        self.assertEqual(plan.runtime_args, {"scope": "runtime"})

    def test_aggregate_status_follows_transaction_status(self) -> None:
        from core.runtime.execution_plan import ExecutionPlan

        transaction = self._transaction()
        transaction.get_operation("op-1").start().succeed()
        transaction.get_operation("op-2").start().fail({"error": "boom"})
        plan = ExecutionPlan("plan-1", self._graph(), transaction)

        self.assertEqual(plan.status, "partial_failed")

    def test_fingerprint_deterministic(self) -> None:
        from core.runtime.execution_plan import ExecutionPlan

        first = ExecutionPlan(
            "plan-1",
            self._graph(),
            self._transaction(),
            runtime_args={"b": 2, "a": 1},
            metadata={"z": 3, "a": 1},
        )
        second = ExecutionPlan(
            "plan-1",
            self._graph(),
            self._transaction(),
            runtime_args={"a": 1, "b": 2},
            metadata={"a": 1, "z": 3},
        )

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_fingerprint_changes_when_graph_dependency_changes(self) -> None:
        from core.runtime.execution_plan import ExecutionPlan
        from core.runtime.runtime_execution_graph import RuntimeExecutionGraph

        graph_without_dependency = RuntimeExecutionGraph()
        graph_without_dependency.add_node("op-1", "lifecycle.queue")
        graph_without_dependency.add_node("op-2", "lifecycle.dispatch")

        first = self._plan()
        second = ExecutionPlan("plan-1", graph_without_dependency, self._transaction())

        self.assertNotEqual(first.fingerprint, second.fingerprint)

    def test_fingerprint_changes_when_operation_changes(self) -> None:
        from core.runtime.execution_plan import ExecutionPlan

        changed = self._transaction()
        changed.get_operation("op-1").start().succeed()

        self.assertNotEqual(
            self._plan().fingerprint,
            ExecutionPlan("plan-1", self._graph(), changed).fingerprint,
        )

    def test_graph_transaction_external_mutation_does_not_break_plan(self) -> None:
        from core.runtime.execution_plan import ExecutionPlan

        graph = self._graph()
        transaction = self._transaction()
        plan = ExecutionPlan("plan-1", graph, transaction)
        graph.add_node("op-3", "recovery.run")
        transaction.add_operation(self._operation("op-3", "recovery.run"))

        self.assertEqual(
            [operation.operation_id for operation in plan.execution_order()],
            ["op-1", "op-2"],
        )

    def test_plan_graph_transaction_properties_return_copy(self) -> None:
        plan = self._plan()
        graph = plan.graph
        transaction = plan.transaction
        graph.add_node("op-3", "recovery.run")
        transaction.add_operation(self._operation("op-3", "recovery.run"))

        self.assertEqual(len(plan.graph.list_nodes()), 2)
        self.assertEqual(len(plan.transaction.list_operations()), 2)

    def test_constructor_inputs_not_mutated(self) -> None:
        from core.runtime.execution_plan import ExecutionPlan

        runtime_args = {"items": [{"scope": "runtime"}]}
        metadata = {"tags": ["contract"]}
        before = copy.deepcopy((runtime_args, metadata))

        ExecutionPlan(
            "plan-1",
            self._graph(),
            self._transaction(),
            runtime_args=runtime_args,
            metadata=metadata,
        )

        self.assertEqual((runtime_args, metadata), before)


if __name__ == "__main__":
    unittest.main()
