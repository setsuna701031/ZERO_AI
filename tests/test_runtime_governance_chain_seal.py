from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeGovernanceChainSealTest(unittest.TestCase):
    def _valid_boundary(self) -> dict:
        return {
            "boundary_id": "boundary-1",
            "boundary_state": "boundary_ready",
            "execution_intent": "governed_mutation",
            "capability_grant_state": "grant_valid",
            "approval_state": "approval_valid",
            "transaction_state": "sealed",
            "transition_valid": True,
            "rollback_state": "rollback_ready",
            "verification_state": "verification_passed",
            "seal_state": "seal_ready",
            "replay_consistency_state": "replay_consistent",
            "evidence_chain_valid": True,
            "evidence_integrity_state": "valid",
            "replay_evidence_consistent": True,
            "evidence_tamper_detected": False,
            "evidence_seal_valid": True,
            "reconstruction_state": "consistent",
            "reconstruction_consistent": True,
            "replay_order_valid": True,
            "reconstruction_divergence_detected": False,
            "rollback_reconstruction_valid": True,
            "seal_reconstruction_valid": True,
            "blocking_issues": [],
            "reason_codes": [],
        }

    def _seal(self, boundary: dict | None = None) -> dict:
        from core.runtime.runtime_governance_chain_seal import (
            build_runtime_governance_chain_seal_report,
        )

        return build_runtime_governance_chain_seal_report(
            boundary_report=copy.deepcopy(boundary or self._valid_boundary())
        )

    def test_fully_valid_chain_is_sealable(self) -> None:
        from core.runtime.runtime_governance_chain_seal import (
            validate_runtime_governance_chain_seal_report,
        )

        report = self._seal()
        validation = validate_runtime_governance_chain_seal_report(report)

        self.assertTrue(report["governance_chain_seal_id"].startswith("runtime-governance-chain-seal-"))
        self.assertTrue(report["governance_chain_sealable"])
        self.assertEqual(report["governance_chain_state"], "sealable")
        self.assertEqual(report["seal_blockers"], [])
        self.assertEqual(report["seal_warnings"], [])
        self.assertTrue(validation["ok"])

    def test_blocked_boundary_prevents_seal(self) -> None:
        boundary = self._valid_boundary()
        boundary["boundary_state"] = "blocked"

        report = self._seal(boundary)

        self.assertFalse(report["governance_chain_sealable"])
        self.assertEqual(report["governance_chain_state"], "blocked")
        self.assertIn("boundary_blocked", report["seal_summary"]["reason_codes"])

    def test_missing_capability_prevents_seal(self) -> None:
        boundary = self._valid_boundary()
        boundary["capability_grant_state"] = "grant_missing"

        report = self._seal(boundary)

        self.assertFalse(report["governance_chain_sealable"])
        self.assertIn("capability_grant_not_valid", report["seal_summary"]["reason_codes"])

    def test_invalid_approval_prevents_seal(self) -> None:
        boundary = self._valid_boundary()
        boundary["approval_state"] = "approval_mismatch"

        report = self._seal(boundary)

        self.assertFalse(report["governance_chain_sealable"])
        self.assertIn("approval_chain_not_valid", report["seal_summary"]["reason_codes"])

    def test_invalid_transaction_transition_prevents_seal(self) -> None:
        boundary = self._valid_boundary()
        boundary["transition_valid"] = False

        report = self._seal(boundary)

        self.assertFalse(report["governance_chain_sealable"])
        self.assertIn("transaction_transition_invalid", report["seal_summary"]["reason_codes"])

    def test_broken_evidence_prevents_seal(self) -> None:
        boundary = self._valid_boundary()
        boundary["evidence_chain_valid"] = False
        boundary["evidence_integrity_state"] = "broken_linkage"

        report = self._seal(boundary)

        self.assertFalse(report["governance_chain_sealable"])
        self.assertIn("evidence_chain_invalid", report["seal_summary"]["reason_codes"])
        self.assertIn("evidence_integrity_invalid", report["seal_summary"]["reason_codes"])

    def test_reconstruction_divergence_prevents_seal(self) -> None:
        boundary = self._valid_boundary()
        boundary["reconstruction_divergence_detected"] = True

        report = self._seal(boundary)

        self.assertFalse(report["governance_chain_sealable"])
        self.assertIn("reconstruction_divergence_detected", report["seal_summary"]["reason_codes"])

    def test_rollback_unavailable_prevents_seal(self) -> None:
        boundary = self._valid_boundary()
        boundary["rollback_state"] = "rollback_unavailable"

        report = self._seal(boundary)

        self.assertFalse(report["governance_chain_sealable"])
        self.assertIn("rollback_unavailable", report["seal_summary"]["reason_codes"])

    def test_verification_failed_prevents_seal(self) -> None:
        boundary = self._valid_boundary()
        boundary["verification_state"] = "verification_failed"

        report = self._seal(boundary)

        self.assertFalse(report["governance_chain_sealable"])
        self.assertIn("verification_failed", report["seal_summary"]["reason_codes"])

    def test_warnings_do_not_block_seal(self) -> None:
        boundary = self._valid_boundary()
        boundary["transaction_state"] = ""
        boundary["verification_state"] = "not_applicable"
        boundary["rollback_state"] = "not_applicable"
        boundary["seal_state"] = "not_applicable"
        boundary["evidence_integrity_state"] = "not_applicable"
        boundary["reconstruction_state"] = "not_applicable"

        report = self._seal(boundary)

        self.assertTrue(report["governance_chain_sealable"])
        self.assertEqual(report["governance_chain_state"], "warning")
        self.assertEqual(report["seal_blockers"], [])
        self.assertGreater(len(report["seal_warnings"]), 0)

    def test_seal_summary_is_deterministic(self) -> None:
        first = self._seal()
        second = self._seal()

        self.assertEqual(first["governance_chain_seal_id"], second["governance_chain_seal_id"])
        self.assertEqual(first["seal_summary"], second["seal_summary"])
        self.assertEqual(first["decision_inputs"], second["decision_inputs"])


if __name__ == "__main__":
    unittest.main()
