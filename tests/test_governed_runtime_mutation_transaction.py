from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class GovernedRuntimeMutationTransactionTest(unittest.TestCase):
    def _transaction(self, state: str = "prepared", **overrides):
        from core.runtime.governed_runtime_mutation_transaction import (
            build_governed_runtime_mutation_transaction_contract,
        )

        payload = build_governed_runtime_mutation_transaction_contract(
            transaction_id="transaction-1",
            transaction_state=state,
            execution_intent="governed_mutation",
            required_capabilities=["runtime.governed_mutation", "runtime.approval"],
            approval_chain_id="approval-1",
            verification_required=True,
            rollback_available=True,
            seal_required=True,
        )
        payload.update(overrides)
        return payload

    def test_valid_lifecycle_transition_flow(self) -> None:
        from core.runtime.governed_runtime_mutation_transaction import (
            validate_governed_runtime_mutation_transaction_lifecycle,
        )

        transitions = [
            ("", "prepared"),
            ("prepared", "awaiting_review"),
            ("awaiting_review", "approved"),
            ("approved", "executing"),
            ("executing", "verification_pending"),
            ("verification_pending", "sealed"),
        ]

        for previous, current in transitions:
            with self.subTest(previous=previous, current=current):
                result = validate_governed_runtime_mutation_transaction_lifecycle(
                    self._transaction(current),
                    previous_transaction_state=previous,
                    verification_report={"ok": True},
                    rollback_report={"available": True},
                    seal_report={"sealed": True},
                    replay_report={"consistent": True},
                )
                self.assertTrue(result["transition_valid"])
                self.assertTrue(result["ok"])

    def test_invalid_transition_blocked(self) -> None:
        from core.runtime.governed_runtime_mutation_transaction import (
            validate_governed_runtime_mutation_transaction_lifecycle,
        )

        result = validate_governed_runtime_mutation_transaction_lifecycle(
            self._transaction("executing"),
            previous_transaction_state="prepared",
            rollback_report={"available": True},
        )

        self.assertFalse(result["ok"])
        self.assertFalse(result["transition_valid"])
        self.assertIn("invalid_transaction_state_transition", result["reason_codes"])

    def test_verification_missing_blocked(self) -> None:
        from core.runtime.governed_runtime_mutation_transaction import (
            validate_governed_runtime_mutation_transaction_lifecycle,
        )

        result = validate_governed_runtime_mutation_transaction_lifecycle(
            self._transaction("verification_pending"),
            previous_transaction_state="executing",
            rollback_report={"available": True},
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["verification_state"], "verification_missing")

    def test_rollback_readiness_enforcement(self) -> None:
        from core.runtime.governed_runtime_mutation_transaction import (
            validate_governed_runtime_mutation_transaction_lifecycle,
        )

        unavailable = validate_governed_runtime_mutation_transaction_lifecycle(
            self._transaction("executing", rollback_available=False),
            previous_transaction_state="approved",
        )
        not_ready = validate_governed_runtime_mutation_transaction_lifecycle(
            self._transaction("executing"),
            previous_transaction_state="approved",
        )

        self.assertEqual(unavailable["rollback_state"], "rollback_unavailable")
        self.assertEqual(not_ready["rollback_state"], "rollback_not_ready")
        self.assertFalse(unavailable["ok"])
        self.assertFalse(not_ready["ok"])

    def test_seal_readiness_enforcement(self) -> None:
        from core.runtime.governed_runtime_mutation_transaction import (
            validate_governed_runtime_mutation_transaction_lifecycle,
        )

        result = validate_governed_runtime_mutation_transaction_lifecycle(
            self._transaction("sealed"),
            previous_transaction_state="verification_pending",
            verification_report={"ok": True},
            rollback_report={"available": True},
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["seal_state"], "seal_missing")

    def test_replay_consistency_validation(self) -> None:
        from core.runtime.governed_runtime_mutation_transaction import (
            validate_governed_runtime_mutation_transaction_lifecycle,
        )

        result = validate_governed_runtime_mutation_transaction_lifecycle(
            self._transaction("verification_pending"),
            previous_transaction_state="executing",
            verification_report={"ok": True},
            rollback_report={"available": True},
            replay_report={"consistent": False},
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["replay_consistency_state"], "replay_inconsistent")

    def test_boundary_blocks_invalid_transaction(self) -> None:
        from tests.test_controlled_runtime_execution_boundary import (
            ControlledRuntimeExecutionBoundaryTest,
        )
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
        )

        helper = ControlledRuntimeExecutionBoundaryTest()
        contract, requests = helper._contract_and_requests()
        report = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=helper._landing_report(),
            capability_grant_contract=helper._capability_grant(),
            approval_chain_contract=helper._approval_chain(),
            mutation_transaction_contract=self._transaction("executing"),
            previous_transaction_state="prepared",
            transaction_rollback_report={"available": True},
        )

        self.assertEqual(report["boundary_state"], "blocked")
        self.assertFalse(report["transition_valid"])
        self.assertEqual(report["transaction_state"], "executing")


if __name__ == "__main__":
    unittest.main()
