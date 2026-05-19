from __future__ import annotations

import unittest

from core.runtime.runtime_lifecycle_coordinator import (
    RuntimeLifecycleCoordinator,
    RuntimeLifecycleRecord,
)


class RuntimeLifecycleCoordinatorContractTest(unittest.TestCase):
    def test_create_record(self) -> None:
        coordinator = RuntimeLifecycleCoordinator()
        result = coordinator.create_record(
            lifecycle_id="lc:1",
            artifact_id="tx:1",
            artifact_type="transaction",
            transaction_id="tx:1",
            lineage={"task_id": "task-1"},
            provenance={"source": "unit-test"},
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.record.state, "created")
        self.assertEqual(result.record.artifact_type, "transaction")
        self.assertEqual(result.record.lineage["task_id"], "task-1")

    def test_active_verify_commit_seal_flow(self) -> None:
        coordinator = RuntimeLifecycleCoordinator()
        coordinator.create_record(lifecycle_id="lc:flow", artifact_id="mut:1", artifact_type="mutation")

        coordinator.mark_active("lc:flow")
        coordinator.mark_verifying("lc:flow")
        coordinator.mark_verified("lc:flow")
        coordinator.commit("lc:flow")
        result = coordinator.seal("lc:flow")

        self.assertTrue(result.record.sealed)
        self.assertEqual(result.record.state, "sealed")
        self.assertTrue(result.record.verified)
        self.assertEqual(len(result.record.transition_history), 5)

    def test_rollback_flow(self) -> None:
        coordinator = RuntimeLifecycleCoordinator()
        coordinator.create_record(lifecycle_id="lc:rollback", artifact_id="mut:2", artifact_type="mutation")

        coordinator.mark_active("lc:rollback")
        coordinator.mark_rollback_required("lc:rollback")
        coordinator.mark_rolling_back("lc:rollback")
        result = coordinator.mark_rolled_back("lc:rollback")

        self.assertEqual(result.record.state, "rolled_back")
        self.assertFalse(result.record.rollback_required)

    def test_invalid_transition_is_blocked(self) -> None:
        coordinator = RuntimeLifecycleCoordinator()
        coordinator.create_record(lifecycle_id="lc:invalid", artifact_id="exec:1", artifact_type="execution")

        result = coordinator.commit("lc:invalid")

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "blocked")
        self.assertIn("invalid_lifecycle_transition", result.decision.reason)
        self.assertEqual(result.record.state, "created")

    def test_sealed_record_is_immutable(self) -> None:
        coordinator = RuntimeLifecycleCoordinator()
        coordinator.create_record(lifecycle_id="lc:sealed", artifact_id="state:1", artifact_type="state")
        coordinator.mark_active("lc:sealed")
        coordinator.mark_verified("lc:sealed")
        coordinator.seal("lc:sealed")

        result = coordinator.fail("lc:sealed")

        self.assertFalse(result.ok)
        self.assertEqual(result.decision.reason, "lifecycle_record_is_sealed")
        self.assertEqual(result.record.state, "sealed")

    def test_parent_lifecycle_requires_existing_parent(self) -> None:
        coordinator = RuntimeLifecycleCoordinator()

        with self.assertRaises(ValueError):
            coordinator.create_record(
                lifecycle_id="lc:child",
                artifact_id="state:child",
                artifact_type="state",
                parent_lifecycle_id="lc:missing",
            )

    def test_nested_lifecycle_parent_id_preserved(self) -> None:
        coordinator = RuntimeLifecycleCoordinator()
        coordinator.create_record(lifecycle_id="lc:parent", artifact_id="tx:parent", artifact_type="transaction")
        child = coordinator.create_record(
            lifecycle_id="lc:child",
            artifact_id="mut:child",
            artifact_type="mutation",
            parent_lifecycle_id="lc:parent",
        )

        self.assertEqual(child.record.parent_lifecycle_id, "lc:parent")

    def test_records_for_transaction(self) -> None:
        coordinator = RuntimeLifecycleCoordinator()
        coordinator.create_record(
            lifecycle_id="lc:tx",
            artifact_id="tx:abc",
            artifact_type="transaction",
            transaction_id="tx:abc",
        )
        coordinator.create_record(
            lifecycle_id="lc:mut",
            artifact_id="mut:abc",
            artifact_type="mutation",
            transaction_id="tx:abc",
        )
        coordinator.create_record(
            lifecycle_id="lc:other",
            artifact_id="mut:other",
            artifact_type="mutation",
            transaction_id="tx:other",
        )

        records = coordinator.records_for_transaction("tx:abc")

        self.assertEqual({record.lifecycle_id for record in records}, {"lc:tx", "lc:mut"})

    def test_unsupported_state_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RuntimeLifecycleRecord(
                lifecycle_id="lc:bad",
                artifact_id="bad",
                artifact_type="transaction",
                state="unknown",
            )

    def test_unsupported_artifact_type_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RuntimeLifecycleRecord(
                lifecycle_id="lc:bad",
                artifact_id="bad",
                artifact_type="unknown",
            )


if __name__ == "__main__":
    unittest.main()
