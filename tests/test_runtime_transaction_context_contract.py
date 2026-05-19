from __future__ import annotations

import unittest

from core.runtime.runtime_transaction_context import (
    RuntimeTransactionBinder,
    RuntimeTransactionContext,
    attach_current_transaction_to_mapping,
    clear_current_transaction,
    current_transaction_metadata,
    get_current_transaction,
    merge_current_transaction_metadata,
    require_current_transaction,
    set_current_transaction,
    transaction_context,
    transaction_scope,
)
from core.runtime.runtime_transaction_coordinator import RuntimeTransactionCoordinator


class RuntimeTransactionContextContractTest(unittest.TestCase):
    def tearDown(self) -> None:
        clear_current_transaction()

    def test_set_get_and_clear_current_transaction(self) -> None:
        context = RuntimeTransactionContext(
            transaction_id="tx:ctx",
            lineage={"task_id": "task-ctx"},
            provenance={"source": "unit-test"},
        )

        previous = set_current_transaction(context)

        self.assertIsNone(previous)
        self.assertEqual(get_current_transaction(), context)
        self.assertEqual(require_current_transaction().transaction_id, "tx:ctx")

        clear_current_transaction()
        self.assertIsNone(get_current_transaction())
        with self.assertRaises(RuntimeError):
            require_current_transaction()

    def test_transaction_context_restores_previous_context(self) -> None:
        outer = RuntimeTransactionContext(transaction_id="tx:outer")
        inner = RuntimeTransactionContext(transaction_id="tx:inner")
        set_current_transaction(outer)

        with transaction_context(inner):
            self.assertEqual(require_current_transaction().transaction_id, "tx:inner")

        self.assertEqual(require_current_transaction().transaction_id, "tx:outer")

    def test_transaction_scope_begins_and_propagates_context(self) -> None:
        coordinator = RuntimeTransactionCoordinator()

        with transaction_scope(
            coordinator,
            transaction_id="tx:scope",
            lineage={"task_id": "task-scope"},
            authority_metadata={"identity_id": "human:1"},
            provenance={"source": "unit-test"},
        ) as context:
            self.assertEqual(context.transaction_id, "tx:scope")
            self.assertEqual(require_current_transaction().transaction_id, "tx:scope")
            scope = coordinator.get_scope("tx:scope")
            self.assertEqual(scope.lineage["task_id"], "task-scope")

        self.assertIsNone(get_current_transaction())
        self.assertEqual(coordinator.get_scope("tx:scope").status, "active")

    def test_transaction_scope_auto_commit_and_seal(self) -> None:
        coordinator = RuntimeTransactionCoordinator()

        with transaction_scope(
            coordinator,
            transaction_id="tx:auto",
            auto_commit=True,
            auto_seal=True,
        ):
            self.assertEqual(require_current_transaction().transaction_id, "tx:auto")

        scope = coordinator.get_scope("tx:auto")
        self.assertEqual(scope.status, "sealed")
        self.assertTrue(scope.sealed)

    def test_transaction_scope_rolls_back_on_exception(self) -> None:
        coordinator = RuntimeTransactionCoordinator()

        with self.assertRaises(ValueError):
            with transaction_scope(coordinator, transaction_id="tx:error"):
                raise ValueError("boom")

        scope = coordinator.get_scope("tx:error")
        self.assertEqual(scope.status, "rolled_back")
        self.assertFalse(scope.rollback_required)

    def test_current_transaction_metadata_empty_without_context(self) -> None:
        self.assertEqual(current_transaction_metadata(), {})

    def test_merge_current_transaction_metadata_attaches_context(self) -> None:
        context = RuntimeTransactionContext(
            transaction_id="tx:merge",
            parent_transaction_id="tx:parent",
            lineage={"task_id": "task-1"},
            provenance={"source": "scope"},
        )
        set_current_transaction(context)

        metadata = merge_current_transaction_metadata(
            {
                "existing": True,
                "lineage": {"step_id": "step-1"},
                "provenance": {"caller": "test"},
            }
        )

        self.assertTrue(metadata["existing"])
        self.assertEqual(metadata["transaction_id"], "tx:merge")
        self.assertEqual(metadata["parent_transaction_id"], "tx:parent")
        self.assertEqual(metadata["lineage"]["task_id"], "task-1")
        self.assertEqual(metadata["lineage"]["step_id"], "step-1")
        self.assertEqual(metadata["provenance"]["source"], "scope")
        self.assertEqual(metadata["provenance"]["caller"], "test")
        self.assertEqual(metadata["runtime_transaction"]["transaction_id"], "tx:merge")

    def test_attach_current_transaction_to_mapping(self) -> None:
        set_current_transaction(RuntimeTransactionContext(transaction_id="tx:payload"))
        payload = attach_current_transaction_to_mapping({"ok": True})

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["transaction_id"], "tx:payload")

    def test_attach_current_transaction_rejects_non_dict(self) -> None:
        with self.assertRaises(TypeError):
            attach_current_transaction_to_mapping([])  # type: ignore[arg-type]

    def test_binder_returns_none_without_context(self) -> None:
        coordinator = RuntimeTransactionCoordinator()
        coordinator.begin_transaction(transaction_id="tx:none")
        binder = RuntimeTransactionBinder(coordinator)

        self.assertIsNone(binder.bind_execution("exec:1"))

    def test_binder_binds_all_runtime_ids_to_current_transaction(self) -> None:
        coordinator = RuntimeTransactionCoordinator()
        binder = RuntimeTransactionBinder(coordinator)

        with transaction_scope(coordinator, transaction_id="tx:bind"):
            binder.bind_execution("exec:1")
            binder.bind_mutation("mut:1")
            binder.bind_state("state:1")
            binder.bind_snapshot("snapshot:1")
            binder.bind_replay("replay:1")
            result = binder.bind_side_effect("effect:1")

        self.assertIsNotNone(result)
        scope = coordinator.get_scope("tx:bind")
        self.assertEqual(scope.execution_ids, ("exec:1",))
        self.assertEqual(scope.mutation_transaction_ids, ("mut:1",))
        self.assertEqual(scope.state_ids, ("state:1",))
        self.assertEqual(scope.snapshot_ids, ("snapshot:1",))
        self.assertEqual(scope.replay_ids, ("replay:1",))
        self.assertEqual(scope.side_effect_ids, ("effect:1",))

    def test_nested_scope_parent_id_propagates(self) -> None:
        coordinator = RuntimeTransactionCoordinator()

        with transaction_scope(coordinator, transaction_id="tx:parent"):
            with transaction_scope(
                coordinator,
                transaction_id="tx:child",
                parent_transaction_id="tx:parent",
            ) as child:
                self.assertEqual(child.parent_transaction_id, "tx:parent")
                self.assertEqual(require_current_transaction().transaction_id, "tx:child")
            self.assertEqual(require_current_transaction().transaction_id, "tx:parent")

        self.assertEqual(coordinator.get_scope("tx:child").parent_transaction_id, "tx:parent")


if __name__ == "__main__":
    unittest.main()
