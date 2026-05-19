from __future__ import annotations

import unittest

from core.runtime.runtime_execution_lifecycle import (
    begin_execution_lifecycle,
    begin_execution_rollback,
    commit_execution_lifecycle,
    execution_lifecycle_id,
    fail_execution_lifecycle,
    finish_execution_rollback,
    mark_execution_verified,
    mark_execution_verifying,
    require_execution_rollback,
    seal_execution_lifecycle,
)
from core.runtime.runtime_lifecycle_context import (
    clear_current_lifecycle_coordinator,
    lifecycle_context,
)
from core.runtime.runtime_lifecycle_coordinator import RuntimeLifecycleCoordinator
from core.runtime.runtime_transaction_context import (
    clear_current_transaction,
    transaction_scope,
)
from core.runtime.runtime_transaction_coordinator import RuntimeTransactionCoordinator


class RuntimeExecutionLifecycleIntegrationTest(unittest.TestCase):
    def tearDown(self) -> None:
        clear_current_lifecycle_coordinator()
        clear_current_transaction()

    def test_execution_success_lifecycle(self) -> None:
        lifecycle = RuntimeLifecycleCoordinator()
        transactions = RuntimeTransactionCoordinator()

        with transaction_scope(
            transactions,
            transaction_id="tx:exec",
            lineage={"task_id": "task-exec"},
            provenance={"source": "execution-test"},
        ):
            with lifecycle_context(lifecycle):
                begin_execution_lifecycle(
                    "exec:1",
                    metadata={"step": "begin"},
                )
                mark_execution_verifying("exec:1")
                mark_execution_verified("exec:1")
                commit_execution_lifecycle("exec:1")
                seal_execution_lifecycle("exec:1")

        record = lifecycle.get_record(execution_lifecycle_id("exec:1"))

        self.assertEqual(record.state, "sealed")
        self.assertTrue(record.sealed)
        self.assertTrue(record.verified)
        self.assertEqual(record.transaction_id, "tx:exec")
        self.assertEqual(record.lineage["task_id"], "task-exec")

    def test_execution_rollback_flow(self) -> None:
        lifecycle = RuntimeLifecycleCoordinator()
        transactions = RuntimeTransactionCoordinator()

        with transaction_scope(transactions, transaction_id="tx:rollback"):
            with lifecycle_context(lifecycle):
                begin_execution_lifecycle("exec:rollback")
                require_execution_rollback("exec:rollback")
                begin_execution_rollback("exec:rollback")
                finish_execution_rollback("exec:rollback")

        record = lifecycle.get_record(execution_lifecycle_id("exec:rollback"))

        self.assertEqual(record.state, "rolled_back")

    def test_execution_failure_flow(self) -> None:
        lifecycle = RuntimeLifecycleCoordinator()
        transactions = RuntimeTransactionCoordinator()

        with transaction_scope(transactions, transaction_id="tx:fail"):
            with lifecycle_context(lifecycle):
                begin_execution_lifecycle("exec:fail")
                fail_execution_lifecycle("exec:fail")

        record = lifecycle.get_record(execution_lifecycle_id("exec:fail"))

        self.assertEqual(record.state, "failed")

    def test_execution_lifecycle_id(self) -> None:
        self.assertEqual(
            execution_lifecycle_id("exec:test"),
            "lifecycle:execution:exec:test",
        )


if __name__ == "__main__":
    unittest.main()
