from __future__ import annotations

import unittest

from core.runtime.runtime_lifecycle_context import (
    clear_current_lifecycle_coordinator,
    create_current_lifecycle_record,
    get_current_lifecycle_coordinator,
    lifecycle_context,
    lifecycle_id_for_artifact,
    mark_current_lifecycle_active,
    mark_current_lifecycle_committed,
    mark_current_lifecycle_verified,
    set_current_lifecycle_coordinator,
    transition_current_lifecycle,
)
from core.runtime.runtime_lifecycle_coordinator import RuntimeLifecycleCoordinator
from core.runtime.runtime_transaction_context import clear_current_transaction, transaction_scope
from core.runtime.runtime_transaction_coordinator import RuntimeTransactionCoordinator


class RuntimeLifecycleBindingIntegrationTest(unittest.TestCase):
    def tearDown(self) -> None:
        clear_current_lifecycle_coordinator()
        clear_current_transaction()

    def test_lifecycle_context_sets_and_restores_coordinator(self) -> None:
        coordinator = RuntimeLifecycleCoordinator()

        with lifecycle_context(coordinator):
            self.assertIs(get_current_lifecycle_coordinator(), coordinator)

        self.assertIsNone(get_current_lifecycle_coordinator())

    def test_create_current_lifecycle_record_is_noop_without_coordinator(self) -> None:
        result = create_current_lifecycle_record(
            lifecycle_id="lc:none",
            artifact_id="state:none",
            artifact_type="state",
        )

        self.assertIsNone(result)

    def test_create_and_transition_current_lifecycle(self) -> None:
        coordinator = RuntimeLifecycleCoordinator()

        with lifecycle_context(coordinator):
            created = create_current_lifecycle_record(
                lifecycle_id="lc:state",
                artifact_id="state:1",
                artifact_type="state",
                lineage={"task_id": "task-1"},
                provenance={"source": "unit-test"},
            )
            self.assertIsNotNone(created)
            mark_current_lifecycle_active("lc:state")
            mark_current_lifecycle_verified("lc:state")
            committed = mark_current_lifecycle_committed("lc:state")

        self.assertIsNotNone(committed)
        record = coordinator.get_record("lc:state")
        self.assertEqual(record.state, "committed")
        self.assertTrue(record.verified)
        self.assertEqual(record.lineage["task_id"], "task-1")

    def test_transaction_metadata_is_attached_to_lifecycle_record(self) -> None:
        lifecycle = RuntimeLifecycleCoordinator()
        transactions = RuntimeTransactionCoordinator()

        with transaction_scope(
            transactions,
            transaction_id="tx:life",
            lineage={"task_id": "task-life"},
            authority_metadata={"identity_id": "human:1"},
            provenance={"source": "transaction"},
        ):
            with lifecycle_context(lifecycle):
                create_current_lifecycle_record(
                    lifecycle_id="lc:mutation",
                    artifact_id="mutation:1",
                    artifact_type="mutation",
                )

        record = lifecycle.get_record("lc:mutation")
        self.assertEqual(record.transaction_id, "tx:life")
        self.assertEqual(record.lineage["task_id"], "task-life")
        self.assertEqual(record.authority_metadata["identity_id"], "human:1")
        self.assertEqual(record.provenance["source"], "transaction")

    def test_duplicate_lifecycle_create_is_noop(self) -> None:
        coordinator = RuntimeLifecycleCoordinator()

        with lifecycle_context(coordinator):
            first = create_current_lifecycle_record(
                lifecycle_id="lc:dupe",
                artifact_id="state:dupe",
                artifact_type="state",
            )
            second = create_current_lifecycle_record(
                lifecycle_id="lc:dupe",
                artifact_id="state:dupe",
                artifact_type="state",
            )

        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_invalid_transition_is_returned_as_blocked(self) -> None:
        coordinator = RuntimeLifecycleCoordinator()

        with lifecycle_context(coordinator):
            create_current_lifecycle_record(
                lifecycle_id="lc:block",
                artifact_id="exec:block",
                artifact_type="execution",
            )
            result = transition_current_lifecycle("lc:block", "committed")

        self.assertIsNotNone(result)
        self.assertFalse(result.ok)
        self.assertEqual(result.status, "blocked")

    def test_lifecycle_id_for_artifact(self) -> None:
        self.assertEqual(
            lifecycle_id_for_artifact("state", "state:abc"),
            "lifecycle:state:state:abc",
        )

    def test_set_current_lifecycle_coordinator_rejects_invalid_value(self) -> None:
        with self.assertRaises(TypeError):
            set_current_lifecycle_coordinator(object())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
