from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeEvidenceChainTest(unittest.TestCase):
    def _record(self, previous_evidence_id: str = "", transaction_id: str = "transaction-1", **overrides):
        from core.runtime.runtime_evidence_chain import build_runtime_evidence_record

        payload = build_runtime_evidence_record(
            transaction_id=transaction_id,
            execution_intent="governed_mutation",
            boundary_state="boundary_ready",
            approval_chain_id="approval-1",
            capability_grant_id="grant-1",
            verification_state="verified",
            rollback_state="rollback_ready",
            seal_state="sealed",
            previous_evidence_id=previous_evidence_id,
            timestamp="2026-01-01T00:00:00+00:00",
        )
        payload.update(overrides)
        return payload

    def _chain(self):
        first = self._record()
        second = self._record(previous_evidence_id=first["evidence_id"])
        return [first, second]

    def test_valid_evidence_chain_passes(self) -> None:
        from core.runtime.runtime_evidence_chain import validate_runtime_evidence_chain

        chain = self._chain()
        result = validate_runtime_evidence_chain(
            chain,
            transaction_id="transaction-1",
            replay_evidence={"latest_evidence_id": chain[-1]["evidence_id"], "consistent": True},
            seal_evidence={"latest_evidence_id": chain[-1]["evidence_id"], "sealed": True},
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["evidence_chain_valid"])
        self.assertEqual(result["evidence_integrity_state"], "valid")

    def test_broken_linkage_blocked(self) -> None:
        from core.runtime.runtime_evidence_chain import validate_runtime_evidence_chain

        chain = self._chain()
        chain[1] = self._record(previous_evidence_id="missing")
        result = validate_runtime_evidence_chain(chain, transaction_id="transaction-1")

        self.assertFalse(result["ok"])
        self.assertEqual(result["evidence_integrity_state"], "broken_linkage")
        self.assertIn("broken_evidence_linkage", result["reason_codes"])

    def test_replay_mismatch_detection(self) -> None:
        from core.runtime.runtime_evidence_chain import validate_runtime_evidence_chain

        chain = self._chain()
        result = validate_runtime_evidence_chain(
            chain,
            transaction_id="transaction-1",
            replay_evidence={"latest_evidence_id": "other", "consistent": True},
        )

        self.assertFalse(result["ok"])
        self.assertFalse(result["replay_evidence_consistent"])
        self.assertEqual(result["evidence_integrity_state"], "replay_mismatch")

    def test_tampered_evidence_detection(self) -> None:
        from core.runtime.runtime_evidence_chain import validate_runtime_evidence_chain

        chain = self._chain()
        chain[0]["verification_state"] = "tampered"
        result = validate_runtime_evidence_chain(chain, transaction_id="transaction-1")

        self.assertFalse(result["ok"])
        self.assertTrue(result["evidence_tamper_detected"])
        self.assertEqual(result["evidence_integrity_state"], "tampered")

    def test_seal_evidence_validation(self) -> None:
        from core.runtime.runtime_evidence_chain import validate_runtime_evidence_chain

        chain = self._chain()
        result = validate_runtime_evidence_chain(
            chain,
            transaction_id="transaction-1",
            seal_evidence={"latest_evidence_id": chain[-1]["evidence_id"], "sealed": False},
        )

        self.assertFalse(result["ok"])
        self.assertFalse(result["evidence_seal_valid"])
        self.assertEqual(result["evidence_integrity_state"], "invalid_seal")

    def test_transaction_evidence_continuity_validation(self) -> None:
        from tests.test_controlled_runtime_execution_boundary import (
            ControlledRuntimeExecutionBoundaryTest,
        )
        from tests.test_governed_runtime_mutation_transaction import (
            GovernedRuntimeMutationTransactionTest,
        )
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
        )

        helper = ControlledRuntimeExecutionBoundaryTest()
        tx_helper = GovernedRuntimeMutationTransactionTest()
        contract, requests = helper._contract_and_requests()
        chain = self._chain()

        report = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=helper._landing_report(),
            capability_grant_contract=helper._capability_grant(),
            approval_chain_contract=helper._approval_chain(),
            mutation_transaction_contract=tx_helper._transaction("sealed"),
            previous_transaction_state="verification_pending",
            transaction_verification_report={"ok": True},
            transaction_rollback_report={"available": True},
            transaction_seal_report={"sealed": True},
            transaction_replay_report={"consistent": True},
            evidence_chain_records=chain,
            replay_evidence={"latest_evidence_id": chain[-1]["evidence_id"], "consistent": True},
            seal_evidence={"latest_evidence_id": chain[-1]["evidence_id"], "sealed": True},
        )

        self.assertEqual(report["boundary_state"], "boundary_ready")
        self.assertTrue(report["evidence_chain_valid"])
        self.assertEqual(report["transaction_state"], "sealed")

    def test_boundary_blocks_broken_evidence_chain(self) -> None:
        from tests.test_controlled_runtime_execution_boundary import (
            ControlledRuntimeExecutionBoundaryTest,
        )
        from tests.test_governed_runtime_mutation_transaction import (
            GovernedRuntimeMutationTransactionTest,
        )
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
        )

        helper = ControlledRuntimeExecutionBoundaryTest()
        tx_helper = GovernedRuntimeMutationTransactionTest()
        contract, requests = helper._contract_and_requests()
        chain = copy.deepcopy(self._chain())
        chain[1] = self._record(previous_evidence_id="missing")

        report = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=helper._landing_report(),
            capability_grant_contract=helper._capability_grant(),
            approval_chain_contract=helper._approval_chain(),
            mutation_transaction_contract=tx_helper._transaction("sealed"),
            previous_transaction_state="verification_pending",
            transaction_verification_report={"ok": True},
            transaction_rollback_report={"available": True},
            transaction_seal_report={"sealed": True},
            transaction_replay_report={"consistent": True},
            evidence_chain_records=chain,
        )

        self.assertEqual(report["boundary_state"], "blocked")
        self.assertFalse(report["evidence_chain_valid"])
        self.assertEqual(report["evidence_integrity_state"], "broken_linkage")


if __name__ == "__main__":
    unittest.main()
