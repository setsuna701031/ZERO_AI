from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeRecoveryReconstructionTest(unittest.TestCase):
    def _chain(self):
        from tests.test_runtime_evidence_chain import RuntimeEvidenceChainTest

        return RuntimeEvidenceChainTest()._chain()

    def _transaction(self):
        from tests.test_governed_runtime_mutation_transaction import (
            GovernedRuntimeMutationTransactionTest,
        )

        return GovernedRuntimeMutationTransactionTest()._transaction("sealed")

    def _reconstruction(self, chain=None, transaction_id: str = "transaction-1", **overrides):
        from core.runtime.runtime_recovery_reconstruction import (
            build_runtime_recovery_reconstruction_contract,
        )

        payload = build_runtime_recovery_reconstruction_contract(
            source_transaction_id=transaction_id,
            source_evidence_chain=self._chain() if chain is None else chain,
            reconstructed_runtime_state={"transaction_id": transaction_id, "state": "sealed"},
            reconstruction_consistent=True,
        )
        payload.update(overrides)
        return payload

    def test_successful_reconstruction(self) -> None:
        from core.runtime.runtime_recovery_reconstruction import (
            validate_runtime_recovery_reconstruction,
        )

        chain = self._chain()
        result = validate_runtime_recovery_reconstruction(
            self._reconstruction(chain=chain),
            transaction_contract=self._transaction(),
            expected_evidence_chain=chain,
            rollback_reconstruction={"valid": True},
            seal_reconstruction={"valid": True, "latest_evidence_id": chain[-1]["evidence_id"]},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["reconstruction_state"], "consistent")
        self.assertTrue(result["reconstruction_consistent"])

    def test_missing_evidence_failure(self) -> None:
        from core.runtime.runtime_recovery_reconstruction import (
            validate_runtime_recovery_reconstruction,
        )

        result = validate_runtime_recovery_reconstruction(
            self._reconstruction(chain=[]),
            transaction_contract=self._transaction(),
            rollback_reconstruction={"valid": True},
            seal_reconstruction={"valid": True},
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reconstruction_state"], "failed")
        self.assertIn("missing_evidence_reconstruction", result["reason_codes"])

    def test_replay_order_mismatch_detection(self) -> None:
        from core.runtime.runtime_recovery_reconstruction import (
            validate_runtime_recovery_reconstruction,
        )

        chain = self._chain()
        reversed_chain = list(reversed(chain))
        result = validate_runtime_recovery_reconstruction(
            self._reconstruction(chain=reversed_chain),
            transaction_contract=self._transaction(),
            rollback_reconstruction={"valid": True},
            seal_reconstruction={"valid": True, "latest_evidence_id": reversed_chain[-1]["evidence_id"]},
        )

        self.assertFalse(result["ok"])
        self.assertFalse(result["replay_order_valid"])
        self.assertIn("replay_order_mismatch", result["reason_codes"])

    def test_divergence_detection(self) -> None:
        from core.runtime.runtime_recovery_reconstruction import (
            validate_runtime_recovery_reconstruction,
        )

        chain = self._chain()
        diverged = copy.deepcopy(chain)
        diverged[-1]["evidence_id"] = "other"
        result = validate_runtime_recovery_reconstruction(
            self._reconstruction(chain=diverged),
            transaction_contract=self._transaction(),
            expected_evidence_chain=chain,
            rollback_reconstruction={"valid": True},
            seal_reconstruction={"valid": True, "latest_evidence_id": diverged[-1]["evidence_id"]},
        )

        self.assertFalse(result["ok"])
        self.assertTrue(result["reconstruction_divergence_detected"])

    def test_rollback_reconstruction_validation(self) -> None:
        from core.runtime.runtime_recovery_reconstruction import (
            validate_runtime_recovery_reconstruction,
        )

        chain = self._chain()
        result = validate_runtime_recovery_reconstruction(
            self._reconstruction(chain=chain),
            transaction_contract=self._transaction(),
            seal_reconstruction={"valid": True, "latest_evidence_id": chain[-1]["evidence_id"]},
        )

        self.assertFalse(result["ok"])
        self.assertFalse(result["rollback_reconstruction_valid"])
        self.assertIn("invalid_rollback_reconstruction", result["reason_codes"])

    def test_seal_reconstruction_validation(self) -> None:
        from core.runtime.runtime_recovery_reconstruction import (
            validate_runtime_recovery_reconstruction,
        )

        chain = self._chain()
        result = validate_runtime_recovery_reconstruction(
            self._reconstruction(chain=chain),
            transaction_contract=self._transaction(),
            rollback_reconstruction={"valid": True},
            seal_reconstruction={"valid": False, "latest_evidence_id": chain[-1]["evidence_id"]},
        )

        self.assertFalse(result["ok"])
        self.assertFalse(result["seal_reconstruction_valid"])
        self.assertIn("invalid_seal_reconstruction", result["reason_codes"])

    def test_boundary_blocks_reconstruction_divergence(self) -> None:
        from tests.test_controlled_runtime_execution_boundary import (
            ControlledRuntimeExecutionBoundaryTest,
        )
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
        )

        helper = ControlledRuntimeExecutionBoundaryTest()
        chain = self._chain()
        diverged = copy.deepcopy(chain)
        diverged[-1]["evidence_id"] = "other"
        transaction = self._transaction()
        contract, requests = helper._contract_and_requests()
        report = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=helper._landing_report(),
            capability_grant_contract=helper._capability_grant(),
            approval_chain_contract=helper._approval_chain(),
            mutation_transaction_contract=transaction,
            previous_transaction_state="verification_pending",
            transaction_verification_report={"ok": True},
            transaction_rollback_report={"available": True},
            transaction_seal_report={"sealed": True},
            transaction_replay_report={"consistent": True},
            evidence_chain_records=chain,
            reconstruction_contract=self._reconstruction(chain=diverged),
            reconstruction_expected_evidence_chain=chain,
            rollback_reconstruction={"valid": True},
            seal_reconstruction={"valid": True, "latest_evidence_id": diverged[-1]["evidence_id"]},
        )

        self.assertEqual(report["boundary_state"], "blocked")
        self.assertTrue(report["reconstruction_divergence_detected"])
        self.assertEqual(report["reconstruction_state"], "diverged")


if __name__ == "__main__":
    unittest.main()
