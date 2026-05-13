from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class FakeDispatcher:
    def __init__(self, fail_operations=None) -> None:
        self.calls = []
        self.fail_operations = set(fail_operations or [])

    def dispatch(self, operation, runtime_args=None, payload=None, metadata=None):
        self.calls.append(
            {
                "operation": operation,
                "runtime_args": runtime_args,
                "payload": payload,
                "metadata": metadata,
            }
        )
        if operation in self.fail_operations:
            raise ValueError(f"failed {operation}")

        return {
            "operation": operation,
            "runtime_args": runtime_args,
            "payload": payload,
            "metadata": metadata,
            "call": len(self.calls),
        }


class RuntimeExecutionTransactionContractTest(unittest.TestCase):
    def _manager(self, dispatcher=None):
        from core.runtime.runtime_execution_transaction import (
            RuntimeExecutionTransactionManager,
        )

        return RuntimeExecutionTransactionManager(
            dispatcher=dispatcher if dispatcher is not None else FakeDispatcher()
        )

    def test_begin_creates_transaction(self) -> None:
        transaction = self._manager().begin("tx-1")

        self.assertEqual(transaction.transaction_id, "tx-1")
        self.assertEqual(transaction.status, "created")
        self.assertFalse(transaction.committed)
        self.assertFalse(transaction.rolled_back)

    def test_empty_transaction_id_rejected(self) -> None:
        from core.runtime.runtime_execution_transaction import (
            RuntimeExecutionTransactionRejected,
        )

        with self.assertRaises(RuntimeExecutionTransactionRejected):
            self._manager().begin("")

    def test_duplicate_transaction_id_rejected(self) -> None:
        from core.runtime.runtime_execution_transaction import (
            RuntimeExecutionTransactionRejected,
        )

        manager = self._manager()
        manager.begin("tx-1")

        with self.assertRaises(RuntimeExecutionTransactionRejected):
            manager.begin("tx-1")

    def test_add_step_to_created_transaction(self) -> None:
        manager = self._manager()
        manager.begin("tx-1")
        step = manager.add_step(
            "tx-1",
            "lifecycle.queue",
            runtime_args={"lifecycle_id": "life-1"},
        )

        self.assertEqual(step.status, "pending")
        self.assertEqual(step.operation, "lifecycle.queue")

    def test_add_step_rejected_after_run_completed(self) -> None:
        from core.runtime.runtime_execution_transaction import (
            RuntimeExecutionTransactionRejected,
        )

        manager = self._manager()
        manager.begin("tx-1")
        manager.add_step("tx-1", "lifecycle.queue")
        manager.run("tx-1")

        with self.assertRaises(RuntimeExecutionTransactionRejected):
            manager.add_step("tx-1", "lifecycle.dispatch")

    def test_empty_operation_rejected(self) -> None:
        from core.runtime.runtime_execution_transaction import (
            RuntimeExecutionTransactionRejected,
        )

        manager = self._manager()
        manager.begin("tx-1")

        with self.assertRaises(RuntimeExecutionTransactionRejected):
            manager.add_step("tx-1", "")

    def test_step_sequence_increments_per_transaction(self) -> None:
        manager = self._manager()
        manager.begin("tx-1")
        first = manager.add_step("tx-1", "lifecycle.queue")
        second = manager.add_step("tx-1", "lifecycle.dispatch")
        manager.begin("tx-2")
        other = manager.add_step("tx-2", "lifecycle.queue")

        self.assertEqual([first.sequence, second.sequence, other.sequence], [1, 2, 1])

    def test_transaction_sequence_increments_globally(self) -> None:
        manager = self._manager()
        first = manager.begin("tx-1")
        second = manager.begin("tx-2")

        self.assertEqual([first.sequence, second.sequence], [1, 2])

    def test_run_dispatches_steps_in_order(self) -> None:
        dispatcher = FakeDispatcher()
        manager = self._manager(dispatcher=dispatcher)
        manager.begin("tx-1")
        manager.add_step("tx-1", "lifecycle.queue")
        manager.add_step("tx-1", "lifecycle.dispatch")
        manager.run("tx-1")

        self.assertEqual(
            [call["operation"] for call in dispatcher.calls],
            ["lifecycle.queue", "lifecycle.dispatch"],
        )

    def test_run_marks_transaction_completed(self) -> None:
        manager = self._manager()
        manager.begin("tx-1")
        manager.add_step("tx-1", "lifecycle.queue")
        transaction = manager.run("tx-1")

        self.assertEqual(transaction.status, "completed")

    def test_run_stores_dispatch_results(self) -> None:
        manager = self._manager()
        manager.begin("tx-1")
        manager.add_step("tx-1", "lifecycle.queue")
        transaction = manager.run("tx-1")

        self.assertEqual(transaction.steps[0].status, "completed")
        self.assertEqual(transaction.steps[0].result["operation"], "lifecycle.queue")
        self.assertEqual(transaction.results[0]["operation"], "lifecycle.queue")

    def test_handler_can_override_step_result(self) -> None:
        manager = self._manager()
        manager.begin("tx-1")
        manager.add_step("tx-1", "lifecycle.queue")

        transaction = manager.run(
            "tx-1",
            handler=lambda step, dispatch_result: {
                "handled": step.operation,
                "call": dispatch_result["call"],
            },
        )

        self.assertEqual(transaction.steps[0].result, {"handled": "lifecycle.queue", "call": 1})

    def test_dispatch_failure_marks_transaction_failed(self) -> None:
        manager = self._manager(dispatcher=FakeDispatcher(fail_operations={"bad.op"}))
        manager.begin("tx-1")
        manager.add_step("tx-1", "bad.op")

        with self.assertRaises(Exception):
            manager.run("tx-1")

        self.assertEqual(manager.get_transaction("tx-1").status, "failed")
        self.assertEqual(manager.get_transaction("tx-1").steps[0].status, "failed")

    def test_dispatch_failure_wraps_runtime_execution_transaction_rejected(self) -> None:
        from core.runtime.runtime_execution_transaction import (
            RuntimeExecutionTransactionRejected,
        )

        manager = self._manager(dispatcher=FakeDispatcher(fail_operations={"bad.op"}))
        manager.begin("tx-1")
        manager.add_step("tx-1", "bad.op")

        with self.assertRaises(RuntimeExecutionTransactionRejected) as context:
            manager.run("tx-1")

        self.assertIsNotNone(context.exception.original_exception)

    def test_pending_steps_skipped_after_failure(self) -> None:
        manager = self._manager(dispatcher=FakeDispatcher(fail_operations={"bad.op"}))
        manager.begin("tx-1")
        manager.add_step("tx-1", "lifecycle.queue")
        manager.add_step("tx-1", "bad.op")
        manager.add_step("tx-1", "lifecycle.dispatch")

        with self.assertRaises(Exception):
            manager.run("tx-1")

        self.assertEqual(
            [step.status for step in manager.get_transaction("tx-1").steps],
            ["completed", "failed", "skipped"],
        )

    def test_commit_requires_completed(self) -> None:
        from core.runtime.runtime_execution_transaction import (
            RuntimeExecutionTransactionRejected,
        )

        manager = self._manager()
        manager.begin("tx-1")

        with self.assertRaises(RuntimeExecutionTransactionRejected):
            manager.commit("tx-1")

    def test_commit_marks_committed(self) -> None:
        manager = self._manager()
        manager.begin("tx-1")
        manager.add_step("tx-1", "lifecycle.queue")
        manager.run("tx-1")
        transaction = manager.commit("tx-1")

        self.assertEqual(transaction.status, "committed")
        self.assertTrue(transaction.committed)

    def test_rollback_allowed_from_created(self) -> None:
        manager = self._manager()
        manager.begin("tx-1")
        transaction = manager.rollback("tx-1")

        self.assertEqual(transaction.status, "rolled_back")
        self.assertTrue(transaction.rolled_back)

    def test_rollback_allowed_from_completed(self) -> None:
        manager = self._manager()
        manager.begin("tx-1")
        manager.add_step("tx-1", "lifecycle.queue")
        manager.run("tx-1")
        transaction = manager.rollback("tx-1")

        self.assertEqual(transaction.status, "rolled_back")

    def test_rollback_allowed_from_failed(self) -> None:
        manager = self._manager(dispatcher=FakeDispatcher(fail_operations={"bad.op"}))
        manager.begin("tx-1")
        manager.add_step("tx-1", "bad.op")
        with self.assertRaises(Exception):
            manager.run("tx-1")

        transaction = manager.rollback("tx-1")

        self.assertEqual(transaction.status, "rolled_back")

    def test_rollback_rejected_after_committed(self) -> None:
        from core.runtime.runtime_execution_transaction import (
            RuntimeExecutionTransactionRejected,
        )

        manager = self._manager()
        manager.begin("tx-1")
        manager.add_step("tx-1", "lifecycle.queue")
        manager.run("tx-1")
        manager.commit("tx-1")

        with self.assertRaises(RuntimeExecutionTransactionRejected):
            manager.rollback("tx-1")

    def test_rolled_back_transaction_cannot_run(self) -> None:
        from core.runtime.runtime_execution_transaction import (
            RuntimeExecutionTransactionRejected,
        )

        manager = self._manager()
        manager.begin("tx-1")
        manager.rollback("tx-1")

        with self.assertRaises(RuntimeExecutionTransactionRejected):
            manager.run("tx-1")

    def test_committed_transaction_cannot_run(self) -> None:
        from core.runtime.runtime_execution_transaction import (
            RuntimeExecutionTransactionRejected,
        )

        manager = self._manager()
        manager.begin("tx-1")
        manager.add_step("tx-1", "lifecycle.queue")
        manager.run("tx-1")
        manager.commit("tx-1")

        with self.assertRaises(RuntimeExecutionTransactionRejected):
            manager.run("tx-1")

    def test_committed_transaction_cannot_add_step(self) -> None:
        from core.runtime.runtime_execution_transaction import (
            RuntimeExecutionTransactionRejected,
        )

        manager = self._manager()
        manager.begin("tx-1")
        manager.add_step("tx-1", "lifecycle.queue")
        manager.run("tx-1")
        manager.commit("tx-1")

        with self.assertRaises(RuntimeExecutionTransactionRejected):
            manager.add_step("tx-1", "lifecycle.dispatch")

    def test_rolled_back_transaction_cannot_add_step(self) -> None:
        from core.runtime.runtime_execution_transaction import (
            RuntimeExecutionTransactionRejected,
        )

        manager = self._manager()
        manager.begin("tx-1")
        manager.rollback("tx-1")

        with self.assertRaises(RuntimeExecutionTransactionRejected):
            manager.add_step("tx-1", "lifecycle.queue")

    def test_payload_preserved(self) -> None:
        payload = {"task_id": "task-1"}
        manager = self._manager()
        transaction = manager.begin("tx-1", payload=payload)
        step = manager.add_step("tx-1", "lifecycle.queue", payload=payload)

        self.assertIs(transaction.payload, payload)
        self.assertIs(step.payload, payload)

    def test_metadata_preserved(self) -> None:
        metadata = {"source": "contract"}
        manager = self._manager()
        transaction = manager.begin("tx-1", metadata=metadata)
        step = manager.add_step("tx-1", "lifecycle.queue", metadata=metadata)

        self.assertIs(transaction.metadata, metadata)
        self.assertIs(step.metadata, metadata)

    def test_runtime_args_preserved(self) -> None:
        runtime_args = {"lifecycle_id": "life-1"}
        manager = self._manager()
        manager.begin("tx-1")
        step = manager.add_step("tx-1", "lifecycle.queue", runtime_args=runtime_args)

        self.assertIs(step.runtime_args, runtime_args)

    def test_payload_not_mutated(self) -> None:
        payload = {"items": [{"task_id": "task-1"}]}
        before = copy.deepcopy(payload)
        manager = self._manager()
        manager.begin("tx-1", payload=payload)
        manager.add_step("tx-1", "lifecycle.queue", payload=payload)
        manager.run("tx-1")

        self.assertEqual(payload, before)

    def test_metadata_not_mutated(self) -> None:
        metadata = {"tags": ["contract"]}
        before = copy.deepcopy(metadata)
        manager = self._manager()
        manager.begin("tx-1", metadata=metadata)
        manager.add_step("tx-1", "lifecycle.queue", metadata=metadata)
        manager.run("tx-1")

        self.assertEqual(metadata, before)

    def test_runtime_args_not_mutated(self) -> None:
        runtime_args = {"lifecycle_id": "life-1", "tags": ["contract"]}
        before = copy.deepcopy(runtime_args)
        manager = self._manager()
        manager.begin("tx-1")
        manager.add_step("tx-1", "lifecycle.queue", runtime_args=runtime_args)
        manager.run("tx-1")

        self.assertEqual(runtime_args, before)

    def test_get_transaction_returns_copy(self) -> None:
        manager = self._manager()
        manager.begin("tx-1")
        manager.add_step("tx-1", "lifecycle.queue")
        transaction = manager.get_transaction("tx-1")
        transaction.status = "polluted"
        transaction.steps[0].status = "polluted"

        current = manager.get_transaction("tx-1")
        self.assertEqual(current.status, "created")
        self.assertEqual(current.steps[0].status, "pending")

    def test_get_transactions_returns_copy(self) -> None:
        manager = self._manager()
        manager.begin("tx-1")
        transactions = manager.get_transactions()
        transactions[0].status = "polluted"
        transactions.clear()

        current = manager.get_transactions()
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0].status, "created")

    def test_clear_resets_manager_and_sequence(self) -> None:
        manager = self._manager()
        manager.begin("tx-1")
        manager.clear()
        transaction = manager.begin("tx-2")

        self.assertEqual(transaction.sequence, 1)
        self.assertEqual(len(manager.get_transactions()), 1)


if __name__ == "__main__":
    unittest.main()
