from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeExecutionPlannerContractTest(unittest.TestCase):
    def _operation(self, operation="lifecycle.queue", transaction_id=None):
        request = {
            "operation": operation,
            "runtime_args": {"lifecycle_id": "life-1"},
            "payload": {"task_id": operation},
            "metadata": {"source": "contract"},
        }
        if transaction_id is not None:
            request["transaction_id"] = transaction_id
        return request

    def test_create_plan(self) -> None:
        from core.runtime.runtime_execution_planner import RuntimeExecutionPlanner

        plan = RuntimeExecutionPlanner().create_plan(
            "plan-1",
            [self._operation()],
        )

        self.assertEqual(plan.plan_id, "plan-1")
        self.assertEqual(plan.status, "planned")
        self.assertEqual(len(plan.transactions), 1)

    def test_empty_plan_id_rejected(self) -> None:
        from core.runtime.runtime_execution_planner import (
            RuntimeExecutionPlanRejected,
            RuntimeExecutionPlanner,
        )

        with self.assertRaises(RuntimeExecutionPlanRejected):
            RuntimeExecutionPlanner().create_plan("", [self._operation()])

    def test_duplicate_plan_id_rejected(self) -> None:
        from core.runtime.runtime_execution_planner import (
            RuntimeExecutionPlanRejected,
            RuntimeExecutionPlanner,
        )

        planner = RuntimeExecutionPlanner()
        planner.create_plan("plan-1", [self._operation()])

        with self.assertRaises(RuntimeExecutionPlanRejected):
            planner.create_plan("plan-1", [self._operation()])

    def test_empty_operations_rejected(self) -> None:
        from core.runtime.runtime_execution_planner import (
            RuntimeExecutionPlanRejected,
            RuntimeExecutionPlanner,
        )

        with self.assertRaises(RuntimeExecutionPlanRejected):
            RuntimeExecutionPlanner().create_plan("plan-1", [])

    def test_empty_operation_rejected(self) -> None:
        from core.runtime.runtime_execution_planner import (
            RuntimeExecutionPlanRejected,
            RuntimeExecutionPlanner,
        )

        with self.assertRaises(RuntimeExecutionPlanRejected):
            RuntimeExecutionPlanner().create_plan("plan-1", [self._operation("")])

    def test_unknown_operation_rejected(self) -> None:
        from core.runtime.runtime_execution_planner import (
            RuntimeExecutionPlanRejected,
            RuntimeExecutionPlanner,
        )

        with self.assertRaises(RuntimeExecutionPlanRejected) as context:
            RuntimeExecutionPlanner().create_plan(
                "plan-1",
                [self._operation("unknown.operation")],
            )

        self.assertIsNotNone(context.exception.original_exception)

    def test_default_transaction_id_assigned(self) -> None:
        from core.runtime.runtime_execution_planner import RuntimeExecutionPlanner

        plan = RuntimeExecutionPlanner().create_plan("plan-1", [self._operation()])

        self.assertEqual(plan.transactions[0].transaction_id, "plan-1:tx:1")
        self.assertEqual(plan.transactions[0].steps[0].transaction_id, "plan-1:tx:1")

    def test_operations_with_same_transaction_id_grouped(self) -> None:
        from core.runtime.runtime_execution_planner import RuntimeExecutionPlanner

        plan = RuntimeExecutionPlanner().create_plan(
            "plan-1",
            [
                self._operation("lifecycle.queue", transaction_id="tx-1"),
                self._operation("lifecycle.dispatch", transaction_id="tx-1"),
            ],
        )

        self.assertEqual(len(plan.transactions), 1)
        self.assertEqual(
            [step.operation for step in plan.transactions[0].steps],
            ["lifecycle.queue", "lifecycle.dispatch"],
        )

    def test_transaction_order_follows_first_appearance(self) -> None:
        from core.runtime.runtime_execution_planner import RuntimeExecutionPlanner

        plan = RuntimeExecutionPlanner().create_plan(
            "plan-1",
            [
                self._operation("lifecycle.queue", transaction_id="tx-b"),
                self._operation("recovery.run", transaction_id="tx-a"),
                self._operation("lifecycle.dispatch", transaction_id="tx-b"),
            ],
        )

        self.assertEqual(
            [transaction.transaction_id for transaction in plan.transactions],
            ["tx-b", "tx-a"],
        )

    def test_step_order_follows_input_order(self) -> None:
        from core.runtime.runtime_execution_planner import RuntimeExecutionPlanner

        plan = RuntimeExecutionPlanner().create_plan(
            "plan-1",
            [
                self._operation("lifecycle.queue", transaction_id="tx-1"),
                self._operation("lifecycle.dispatch", transaction_id="tx-1"),
                self._operation("lifecycle.start_execution", transaction_id="tx-1"),
            ],
        )

        self.assertEqual(
            [step.operation for step in plan.transactions[0].steps],
            [
                "lifecycle.queue",
                "lifecycle.dispatch",
                "lifecycle.start_execution",
            ],
        )

    def test_operation_metadata_preserved(self) -> None:
        from core.runtime.runtime_execution_planner import RuntimeExecutionPlanner

        step = RuntimeExecutionPlanner().create_plan(
            "plan-1",
            [self._operation("recovery.run")],
        ).transactions[0].steps[0]

        self.assertEqual(step.operation_metadata["operation"], "recovery.run")
        self.assertEqual(step.operation_metadata["target"], "recovery")
        self.assertEqual(step.operation_metadata["risk_level"], "high")

    def test_operation_metadata_is_copy(self) -> None:
        from core.runtime.runtime_execution_planner import RuntimeExecutionPlanner
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        registry = RuntimeOperationRegistry()
        registry.register(
            "custom.audit",
            "custom",
            "audit",
            "custom",
            "low",
            metadata={"tags": ["runtime"]},
        )
        planner = RuntimeExecutionPlanner(operation_registry=registry)
        plan = planner.create_plan("plan-1", [self._operation("custom.audit")])
        plan.transactions[0].steps[0].operation_metadata["metadata"]["tags"].append(
            "polluted"
        )

        current = planner.get_plan("plan-1")
        self.assertEqual(
            current.transactions[0].steps[0].operation_metadata["metadata"],
            {"tags": ["runtime"]},
        )

    def test_plan_sequence_increments_globally(self) -> None:
        from core.runtime.runtime_execution_planner import RuntimeExecutionPlanner

        planner = RuntimeExecutionPlanner()
        first = planner.create_plan("plan-1", [self._operation()])
        second = planner.create_plan("plan-2", [self._operation()])

        self.assertEqual([first.sequence, second.sequence], [1, 2])

    def test_transaction_sequence_increments_per_plan(self) -> None:
        from core.runtime.runtime_execution_planner import RuntimeExecutionPlanner

        plan = RuntimeExecutionPlanner().create_plan(
            "plan-1",
            [
                self._operation("lifecycle.queue", transaction_id="tx-1"),
                self._operation("recovery.run", transaction_id="tx-2"),
            ],
        )

        self.assertEqual(
            [transaction.sequence for transaction in plan.transactions],
            [1, 2],
        )

    def test_step_sequence_increments_per_transaction(self) -> None:
        from core.runtime.runtime_execution_planner import RuntimeExecutionPlanner

        plan = RuntimeExecutionPlanner().create_plan(
            "plan-1",
            [
                self._operation("lifecycle.queue", transaction_id="tx-1"),
                self._operation("lifecycle.dispatch", transaction_id="tx-1"),
                self._operation("recovery.run", transaction_id="tx-2"),
            ],
        )

        self.assertEqual(
            [step.sequence for step in plan.transactions[0].steps],
            [1, 2],
        )
        self.assertEqual(plan.transactions[1].steps[0].sequence, 1)

    def test_payload_preserved(self) -> None:
        from core.runtime.runtime_execution_planner import RuntimeExecutionPlanner

        payload = {"plan": "payload"}
        plan = RuntimeExecutionPlanner().create_plan(
            "plan-1",
            [self._operation()],
            payload=payload,
        )

        self.assertIs(plan.payload, payload)

    def test_metadata_preserved(self) -> None:
        from core.runtime.runtime_execution_planner import RuntimeExecutionPlanner

        metadata = {"source": "contract"}
        plan = RuntimeExecutionPlanner().create_plan(
            "plan-1",
            [self._operation()],
            metadata=metadata,
        )

        self.assertIs(plan.metadata, metadata)

    def test_runtime_args_preserved(self) -> None:
        from core.runtime.runtime_execution_planner import RuntimeExecutionPlanner

        runtime_args = {"lifecycle_id": "life-1"}
        operation = self._operation()
        operation["runtime_args"] = runtime_args
        plan = RuntimeExecutionPlanner().create_plan("plan-1", [operation])

        self.assertIs(plan.transactions[0].steps[0].runtime_args, runtime_args)

    def test_payload_not_mutated(self) -> None:
        from core.runtime.runtime_execution_planner import RuntimeExecutionPlanner

        payload = {"items": [{"id": "one"}]}
        before = copy.deepcopy(payload)
        RuntimeExecutionPlanner().create_plan(
            "plan-1",
            [self._operation()],
            payload=payload,
        )

        self.assertEqual(payload, before)

    def test_metadata_not_mutated(self) -> None:
        from core.runtime.runtime_execution_planner import RuntimeExecutionPlanner

        metadata = {"tags": ["contract"]}
        before = copy.deepcopy(metadata)
        RuntimeExecutionPlanner().create_plan(
            "plan-1",
            [self._operation()],
            metadata=metadata,
        )

        self.assertEqual(metadata, before)

    def test_runtime_args_not_mutated(self) -> None:
        from core.runtime.runtime_execution_planner import RuntimeExecutionPlanner

        runtime_args = {"lifecycle_id": "life-1", "tags": ["contract"]}
        before = copy.deepcopy(runtime_args)
        operation = self._operation()
        operation["runtime_args"] = runtime_args
        RuntimeExecutionPlanner().create_plan("plan-1", [operation])

        self.assertEqual(runtime_args, before)

    def test_get_plan_returns_copy(self) -> None:
        from core.runtime.runtime_execution_planner import RuntimeExecutionPlanner

        planner = RuntimeExecutionPlanner()
        planner.create_plan("plan-1", [self._operation()])
        plan = planner.get_plan("plan-1")
        plan.status = "polluted"
        plan.transactions[0].transaction_id = "polluted"
        plan.transactions[0].steps[0].operation = "polluted"

        current = planner.get_plan("plan-1")
        self.assertEqual(current.status, "planned")
        self.assertEqual(current.transactions[0].transaction_id, "plan-1:tx:1")
        self.assertEqual(current.transactions[0].steps[0].operation, "lifecycle.queue")

    def test_list_plans_returns_copy(self) -> None:
        from core.runtime.runtime_execution_planner import RuntimeExecutionPlanner

        planner = RuntimeExecutionPlanner()
        planner.create_plan("plan-1", [self._operation()])
        plans = planner.list_plans()
        plans[0].status = "polluted"
        plans.clear()

        current = planner.list_plans()
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0].status, "planned")

    def test_clear_resets_planner_and_sequence(self) -> None:
        from core.runtime.runtime_execution_planner import RuntimeExecutionPlanner

        planner = RuntimeExecutionPlanner()
        planner.create_plan("plan-1", [self._operation()])
        planner.clear()
        plan = planner.create_plan("plan-2", [self._operation()])

        self.assertEqual(plan.sequence, 1)
        self.assertEqual(len(planner.list_plans()), 1)

    def test_registry_exception_wraps_runtime_execution_plan_rejected(self) -> None:
        from core.runtime.runtime_execution_planner import (
            RuntimeExecutionPlanRejected,
            RuntimeExecutionPlanner,
        )

        original = ValueError("boom")

        class FailingRegistry:
            def get(self, _operation):
                raise original

        with self.assertRaises(RuntimeExecutionPlanRejected) as context:
            RuntimeExecutionPlanner(operation_registry=FailingRegistry()).create_plan(
                "plan-1",
                [self._operation()],
            )

        self.assertIs(context.exception.original_exception, original)


if __name__ == "__main__":
    unittest.main()
