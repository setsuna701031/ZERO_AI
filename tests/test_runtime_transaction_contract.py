from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeTransactionContractTest(unittest.TestCase):
    def _operation(self, operation_id="op-1"):
        from core.runtime.runtime_operation import RuntimeOperation

        return RuntimeOperation(
            operation_id,
            "lifecycle.queue",
            runtime_args={"lifecycle_id": operation_id},
        )

    def _transaction(self):
        from core.runtime.runtime_transaction import RuntimeTransaction

        return RuntimeTransaction(
            "tx-1",
            runtime_args={"scope": "runtime"},
            metadata={"source": "contract"},
        )

    def test_transaction_id_validation(self) -> None:
        from core.runtime.runtime_transaction import (
            RuntimeTransaction,
            RuntimeTransactionRejected,
        )

        with self.assertRaises(RuntimeTransactionRejected):
            RuntimeTransaction("")

    def test_add_get_list_remove_operation(self) -> None:
        transaction = self._transaction()
        operation = self._operation("op-1")

        added = transaction.add_operation(operation)

        self.assertIs(added, operation)
        self.assertIs(transaction.get_operation("op-1"), operation)
        self.assertEqual(transaction.list_operations(), [operation])
        self.assertIs(transaction.remove_operation("op-1"), operation)
        self.assertEqual(transaction.list_operations(), [])

    def test_duplicate_operation_rejected(self) -> None:
        from core.runtime.runtime_transaction import RuntimeTransactionRejected

        transaction = self._transaction()
        transaction.add_operation(self._operation("op-1"))

        with self.assertRaises(RuntimeTransactionRejected):
            transaction.add_operation(self._operation("op-1"))

    def test_unknown_operation_rejected(self) -> None:
        from core.runtime.runtime_transaction import RuntimeTransactionRejected

        transaction = self._transaction()

        with self.assertRaises(RuntimeTransactionRejected):
            transaction.get_operation("missing")
        with self.assertRaises(RuntimeTransactionRejected):
            transaction.remove_operation("missing")

    def test_insertion_order_deterministic(self) -> None:
        transaction = self._transaction()
        transaction.add_operation(self._operation("op-1"))
        transaction.add_operation(self._operation("op-2"))
        transaction.add_operation(self._operation("op-3"))

        self.assertEqual(
            [operation.operation_id for operation in transaction.list_operations()],
            ["op-1", "op-2", "op-3"],
        )

    def test_list_operations_returns_copy(self) -> None:
        transaction = self._transaction()
        transaction.add_operation(self._operation("op-1"))
        operations = transaction.list_operations()
        operations.clear()

        self.assertEqual(len(transaction.list_operations()), 1)

    def test_metadata_runtime_args_copy_on_read(self) -> None:
        transaction = self._transaction()
        metadata = transaction.metadata
        runtime_args = transaction.runtime_args
        metadata["source"] = "polluted"
        runtime_args["scope"] = "polluted"

        self.assertEqual(transaction.metadata, {"source": "contract"})
        self.assertEqual(transaction.runtime_args, {"scope": "runtime"})

    def test_empty_transaction_status_pending(self) -> None:
        self.assertEqual(self._transaction().status, "pending")

    def test_all_pending_status_pending(self) -> None:
        transaction = self._transaction()
        transaction.add_operation(self._operation("op-1"))

        self.assertEqual(transaction.status, "pending")

    def test_any_running_status_running(self) -> None:
        transaction = self._transaction()
        operation = self._operation("op-1")
        operation.start()
        transaction.add_operation(operation)
        transaction.add_operation(self._operation("op-2"))

        self.assertEqual(transaction.status, "running")

    def test_all_succeeded_status_succeeded(self) -> None:
        transaction = self._transaction()
        first = self._operation("op-1")
        second = self._operation("op-2")
        first.start().succeed()
        second.start().succeed()
        transaction.add_operation(first)
        transaction.add_operation(second)

        self.assertEqual(transaction.status, "succeeded")

    def test_all_failed_status_failed(self) -> None:
        transaction = self._transaction()
        first = self._operation("op-1")
        second = self._operation("op-2")
        first.start().fail({"error": "one"})
        second.start().fail({"error": "two"})
        transaction.add_operation(first)
        transaction.add_operation(second)

        self.assertEqual(transaction.status, "failed")

    def test_all_blocked_status_blocked(self) -> None:
        transaction = self._transaction()
        first = self._operation("op-1")
        second = self._operation("op-2")
        first.start().block({"reason": "one"})
        second.start().block({"reason": "two"})
        transaction.add_operation(first)
        transaction.add_operation(second)

        self.assertEqual(transaction.status, "blocked")

    def test_mixed_failure_status_partial_failed(self) -> None:
        transaction = self._transaction()
        first = self._operation("op-1")
        second = self._operation("op-2")
        first.start().succeed()
        second.start().fail({"error": "two"})
        transaction.add_operation(first)
        transaction.add_operation(second)

        self.assertEqual(transaction.status, "partial_failed")

    def test_mixed_blocked_status_partial_failed(self) -> None:
        transaction = self._transaction()
        first = self._operation("op-1")
        second = self._operation("op-2")
        first.start().succeed()
        second.start().block({"reason": "two"})
        transaction.add_operation(first)
        transaction.add_operation(second)

        self.assertEqual(transaction.status, "partial_failed")

    def test_status_is_derived_not_manual(self) -> None:
        from core.runtime.runtime_transaction import RuntimeTransaction

        self.assertIsNone(RuntimeTransaction.__dict__["status"].fset)

    def test_fingerprint_deterministic(self) -> None:
        from core.runtime.runtime_transaction import RuntimeTransaction

        first = RuntimeTransaction(
            "tx-1",
            runtime_args={"b": 2, "a": 1},
            metadata={"z": 3, "a": 1},
        )
        second = RuntimeTransaction(
            "tx-1",
            runtime_args={"a": 1, "b": 2},
            metadata={"a": 1, "z": 3},
        )
        first.add_operation(self._operation("op-1"))
        second.add_operation(self._operation("op-1"))

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_fingerprint_uses_ordered_operation_fingerprints(self) -> None:
        first = self._transaction()
        second = self._transaction()
        first.add_operation(self._operation("op-1"))
        first.add_operation(self._operation("op-2"))
        second.add_operation(self._operation("op-2"))
        second.add_operation(self._operation("op-1"))

        self.assertNotEqual(first.fingerprint, second.fingerprint)

    def test_fingerprint_changes_after_operation_added(self) -> None:
        transaction = self._transaction()
        before = transaction.fingerprint
        transaction.add_operation(self._operation("op-1"))

        self.assertNotEqual(before, transaction.fingerprint)

    def test_fingerprint_changes_after_operation_removed(self) -> None:
        transaction = self._transaction()
        transaction.add_operation(self._operation("op-1"))
        before = transaction.fingerprint
        transaction.remove_operation("op-1")

        self.assertNotEqual(before, transaction.fingerprint)

    def test_inputs_not_mutated(self) -> None:
        from core.runtime.runtime_transaction import RuntimeTransaction

        runtime_args = {"items": [{"scope": "runtime"}]}
        metadata = {"tags": ["contract"]}
        before = copy.deepcopy((runtime_args, metadata))

        RuntimeTransaction("tx-1", runtime_args=runtime_args, metadata=metadata)

        self.assertEqual((runtime_args, metadata), before)


if __name__ == "__main__":
    unittest.main()
