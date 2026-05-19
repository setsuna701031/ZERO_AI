from __future__ import annotations

import unittest

from core.runtime.runtime_transaction_coordinator import RuntimeTransactionCoordinator


class RuntimeTransactionCoordinatorContractTest(unittest.TestCase):
    def test_begin_transaction_creates_scope(self) -> None:
        coordinator = RuntimeTransactionCoordinator()
        result = coordinator.begin_transaction(
            transaction_id="tx:1",
            lineage={"task_id": "task-1"},
            authority_metadata={"identity_id": "human:1"},
            provenance={"source": "test"},
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.scope.transaction_id, "tx:1")
        self.assertEqual(result.scope.status, "active")
        self.assertEqual(result.scope.lineage["task_id"], "task-1")
        self.assertEqual(result.scope.authority_metadata["identity_id"], "human:1")
        self.assertEqual(result.scope.provenance["source"], "test")

    def test_bind_all_runtime_membership_ids(self) -> None:
        coordinator = RuntimeTransactionCoordinator()
        coordinator.begin_transaction(transaction_id="tx:membership")

        coordinator.bind_execution("tx:membership", "exec:1")
        coordinator.bind_mutation("tx:membership", "mut:1")
        coordinator.bind_state("tx:membership", "state:1")
        coordinator.bind_snapshot("tx:membership", "snapshot:1")
        coordinator.bind_replay("tx:membership", "replay:1")
        result = coordinator.bind_side_effect("tx:membership", "effect:1")

        scope = result.scope
        self.assertEqual(scope.execution_ids, ("exec:1",))
        self.assertEqual(scope.mutation_transaction_ids, ("mut:1",))
        self.assertEqual(scope.state_ids, ("state:1",))
        self.assertEqual(scope.snapshot_ids, ("snapshot:1",))
        self.assertEqual(scope.replay_ids, ("replay:1",))
        self.assertEqual(scope.side_effect_ids, ("effect:1",))

    def test_duplicate_bindings_are_idempotent(self) -> None:
        coordinator = RuntimeTransactionCoordinator()
        coordinator.begin_transaction(transaction_id="tx:dedupe")
        coordinator.bind_execution("tx:dedupe", "exec:1")
        result = coordinator.bind_execution("tx:dedupe", "exec:1")

        self.assertEqual(result.scope.execution_ids, ("exec:1",))

    def test_mark_rollback_required(self) -> None:
        coordinator = RuntimeTransactionCoordinator()
        coordinator.begin_transaction(transaction_id="tx:rollback")
        result = coordinator.mark_rollback_required("tx:rollback", metadata={"reason": "verification_failed"})

        self.assertEqual(result.scope.status, "rollback_required")
        self.assertTrue(result.rollback_required)
        self.assertTrue(result.scope.rollback_required)
        self.assertEqual(result.scope.metadata["reason"], "verification_failed")

    def test_mark_verified(self) -> None:
        coordinator = RuntimeTransactionCoordinator()
        coordinator.begin_transaction(transaction_id="tx:verified")
        result = coordinator.mark_verified("tx:verified")

        self.assertTrue(result.verified)
        self.assertTrue(result.scope.verified)

    def test_commit_closes_transaction(self) -> None:
        coordinator = RuntimeTransactionCoordinator()
        coordinator.begin_transaction(transaction_id="tx:commit")
        result = coordinator.commit("tx:commit")

        self.assertTrue(result.committed)
        self.assertEqual(result.scope.status, "committed")
        with self.assertRaises(RuntimeError):
            coordinator.bind_state("tx:commit", "state:late")

    def test_rollback_closes_transaction(self) -> None:
        coordinator = RuntimeTransactionCoordinator()
        coordinator.begin_transaction(transaction_id="tx:rollback-close")
        result = coordinator.rollback("tx:rollback-close")

        self.assertTrue(result.rolled_back)
        self.assertEqual(result.scope.status, "rolled_back")
        with self.assertRaises(RuntimeError):
            coordinator.bind_state("tx:rollback-close", "state:late")

    def test_committed_transaction_cannot_rollback(self) -> None:
        coordinator = RuntimeTransactionCoordinator()
        coordinator.begin_transaction(transaction_id="tx:no-rollback")
        coordinator.commit("tx:no-rollback")

        with self.assertRaises(RuntimeError):
            coordinator.rollback("tx:no-rollback")

    def test_seal_makes_transaction_immutable(self) -> None:
        coordinator = RuntimeTransactionCoordinator()
        coordinator.begin_transaction(transaction_id="tx:seal")
        result = coordinator.seal("tx:seal")

        self.assertTrue(result.sealed)
        self.assertEqual(result.scope.status, "sealed")
        with self.assertRaises(RuntimeError):
            coordinator.bind_execution("tx:seal", "exec:late")
        with self.assertRaises(RuntimeError):
            coordinator.rollback("tx:seal")

    def test_transaction_lineage_preserved(self) -> None:
        coordinator = RuntimeTransactionCoordinator()
        result = coordinator.begin_transaction(
            transaction_id="tx:lineage",
            lineage={"task_id": "task-a", "repair_id": "repair-a"},
            provenance={"source": "unit-test"},
        )

        coordinator.bind_execution("tx:lineage", "exec:a")
        scope = coordinator.get_scope("tx:lineage")
        self.assertEqual(scope.lineage, result.scope.lineage)
        self.assertEqual(scope.provenance["source"], "unit-test")

    def test_nested_transaction_preserves_parent_id(self) -> None:
        coordinator = RuntimeTransactionCoordinator()
        coordinator.begin_transaction(transaction_id="tx:parent")
        child = coordinator.begin_transaction(
            transaction_id="tx:child",
            parent_transaction_id="tx:parent",
        )

        self.assertEqual(child.scope.parent_transaction_id, "tx:parent")

    def test_missing_parent_rejected(self) -> None:
        coordinator = RuntimeTransactionCoordinator()

        with self.assertRaises(ValueError):
            coordinator.begin_transaction(
                transaction_id="tx:child",
                parent_transaction_id="tx:missing",
            )


if __name__ == "__main__":
    unittest.main()
