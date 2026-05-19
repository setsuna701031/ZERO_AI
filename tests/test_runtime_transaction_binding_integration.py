from __future__ import annotations

import unittest

from core.runtime.runtime_transaction_context import (
    RuntimeTransactionContext,
    bind_current_execution,
    bind_current_mutation,
    bind_current_replay,
    bind_current_side_effect,
    bind_current_snapshot,
    bind_current_state,
    clear_current_transaction,
    get_current_transaction_coordinator,
    set_current_transaction,
    set_current_transaction_coordinator,
    transaction_context,
    transaction_scope,
)
from core.runtime.runtime_transaction_coordinator import RuntimeTransactionCoordinator


class RuntimeTransactionBindingIntegrationTest(unittest.TestCase):
    def tearDown(self) -> None:
        clear_current_transaction()

    def test_bind_helpers_return_none_without_context(self) -> None:
        self.assertIsNone(bind_current_mutation("mut:none"))
        self.assertIsNone(bind_current_state("state:none"))
        self.assertIsNone(bind_current_snapshot("snapshot:none"))
        self.assertIsNone(bind_current_side_effect("effect:none"))

    def test_bind_helpers_return_none_without_coordinator(self) -> None:
        set_current_transaction(RuntimeTransactionContext(transaction_id="tx:no-coordinator"))

        self.assertIsNone(bind_current_mutation("mut:none"))

    def test_transaction_scope_sets_current_coordinator(self) -> None:
        coordinator = RuntimeTransactionCoordinator()

        with transaction_scope(coordinator, transaction_id="tx:coordinator"):
            self.assertIs(get_current_transaction_coordinator(), coordinator)

        self.assertIsNone(get_current_transaction_coordinator())

    def test_bind_current_artifacts_inside_transaction_scope(self) -> None:
        coordinator = RuntimeTransactionCoordinator()

        with transaction_scope(coordinator, transaction_id="tx:bind-artifacts"):
            bind_current_execution("exec:1")
            bind_current_mutation("mutation:1")
            bind_current_state("state:1")
            bind_current_snapshot("snapshot:1")
            bind_current_replay("replay:1")
            result = bind_current_side_effect("effect:1")

        self.assertIsNotNone(result)
        scope = coordinator.get_scope("tx:bind-artifacts")
        self.assertEqual(scope.execution_ids, ("exec:1",))
        self.assertEqual(scope.mutation_transaction_ids, ("mutation:1",))
        self.assertEqual(scope.state_ids, ("state:1",))
        self.assertEqual(scope.snapshot_ids, ("snapshot:1",))
        self.assertEqual(scope.replay_ids, ("replay:1",))
        self.assertEqual(scope.side_effect_ids, ("effect:1",))

    def test_transaction_context_can_attach_coordinator(self) -> None:
        coordinator = RuntimeTransactionCoordinator()
        coordinator.begin_transaction(transaction_id="tx:manual")
        context = RuntimeTransactionContext(transaction_id="tx:manual")

        with transaction_context(context, coordinator=coordinator):
            bind_current_state("state:manual")

        self.assertEqual(coordinator.get_scope("tx:manual").state_ids, ("state:manual",))

    def test_set_current_transaction_can_attach_coordinator(self) -> None:
        coordinator = RuntimeTransactionCoordinator()
        coordinator.begin_transaction(transaction_id="tx:set")
        set_current_transaction(RuntimeTransactionContext(transaction_id="tx:set"), coordinator=coordinator)

        bind_current_mutation("mutation:set")

        self.assertEqual(coordinator.get_scope("tx:set").mutation_transaction_ids, ("mutation:set",))

    def test_set_current_transaction_coordinator_rejects_invalid_value(self) -> None:
        with self.assertRaises(TypeError):
            set_current_transaction_coordinator(object())  # type: ignore[arg-type]

    def test_bind_empty_artifact_id_is_noop(self) -> None:
        coordinator = RuntimeTransactionCoordinator()

        with transaction_scope(coordinator, transaction_id="tx:empty"):
            self.assertIsNone(bind_current_state(""))

        self.assertEqual(coordinator.get_scope("tx:empty").state_ids, ())


if __name__ == "__main__":
    unittest.main()
