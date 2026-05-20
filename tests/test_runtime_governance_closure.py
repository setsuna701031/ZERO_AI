from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeGovernanceClosureTest(unittest.TestCase):
    def _valid_seal(self) -> dict:
        return {
            "schema_version": "runtime_governance_chain_seal.v1",
            "governance_chain_seal_id": "runtime-governance-chain-seal-valid",
            "source_boundary_id": "boundary-1",
            "governance_chain_sealable": True,
            "governance_chain_state": "sealable",
            "seal_blockers": [],
            "seal_warnings": [],
            "seal_summary": {
                "boundary_state": "boundary_ready",
                "execution_intent": "governed_mutation",
                "capability_grant_state": "grant_valid",
                "approval_state": "approval_valid",
                "transaction_state": "sealed",
                "evidence_integrity_state": "valid",
                "reconstruction_state": "consistent",
                "blocker_count": 0,
                "warning_count": 0,
                "reason_codes": [],
            },
            "decision_inputs": {},
        }

    def test_constants_are_compatible(self) -> None:
        from core.runtime.runtime_governance_closure import (
            CLOSURE_BLOCKED,
            CLOSURE_CLOSED,
            CLOSURE_WARNING,
            runtime_governance_closure_required_fields,
            runtime_governance_closure_states,
        )

        self.assertEqual(CLOSURE_CLOSED, "closed")
        self.assertEqual(CLOSURE_BLOCKED, "blocked")
        self.assertEqual(CLOSURE_WARNING, "warning")
        self.assertIn("closure_ready", runtime_governance_closure_required_fields())
        self.assertIn("runtime_governance_freeze_candidate", runtime_governance_closure_required_fields())
        self.assertIn("closed", runtime_governance_closure_states())

    def test_valid_seal_becomes_freeze_candidate(self) -> None:
        from core.runtime.runtime_governance_closure import (
            build_runtime_governance_closure_report,
            validate_runtime_governance_closure_report,
        )

        report = build_runtime_governance_closure_report(governance_chain_seal_report=self._valid_seal())
        validation = validate_runtime_governance_closure_report(report)

        self.assertTrue(report["governance_closure_id"].startswith("runtime-governance-closure-"))
        self.assertTrue(report["closure_ready"])
        self.assertEqual(report["closure_state"], "closed")
        self.assertTrue(report["runtime_governance_freeze_candidate"])
        self.assertEqual(report["freeze_state"], "freeze_candidate")
        self.assertEqual(report["closure_blockers"], [])
        self.assertEqual(report["closure_warnings"], [])
        self.assertTrue(validation["ok"])

    def test_warning_seal_is_freeze_candidate_with_warning(self) -> None:
        from core.runtime.runtime_governance_closure import build_runtime_governance_closure_report

        seal = self._valid_seal()
        seal["governance_chain_state"] = "warning"
        seal["seal_warnings"] = [{"kind": "transaction_state_not_applicable"}]

        report = build_runtime_governance_closure_report(governance_chain_seal_report=seal)

        self.assertTrue(report["closure_ready"])
        self.assertEqual(report["closure_state"], "warning")
        self.assertTrue(report["runtime_governance_freeze_candidate"])
        self.assertEqual(report["freeze_state"], "freeze_warning")
        self.assertGreater(len(report["closure_warnings"]), 0)

    def test_blocked_seal_blocks_closure(self) -> None:
        from core.runtime.runtime_governance_closure import build_runtime_governance_closure_report

        seal = self._valid_seal()
        seal["governance_chain_sealable"] = False
        seal["governance_chain_state"] = "blocked"
        seal["seal_blockers"] = [{"kind": "evidence_chain_invalid"}]

        report = build_runtime_governance_closure_report(governance_chain_seal_report=seal)

        self.assertFalse(report["closure_ready"])
        self.assertEqual(report["closure_state"], "blocked")
        self.assertFalse(report["runtime_governance_freeze_candidate"])
        self.assertEqual(report["freeze_state"], "freeze_blocked")
        self.assertIn("governance_chain_not_sealable", report["closure_summary"]["reason_codes"])
        self.assertIn("seal_blocker", report["closure_summary"]["reason_codes"])

    def test_missing_seal_blocks_closure(self) -> None:
        from core.runtime.runtime_governance_closure import build_runtime_governance_closure_report

        report = build_runtime_governance_closure_report()

        self.assertFalse(report["closure_ready"])
        self.assertEqual(report["closure_state"], "blocked")
        self.assertFalse(report["runtime_governance_freeze_candidate"])
        self.assertIn("governance_chain_seal_missing", report["closure_summary"]["reason_codes"])

    def test_closure_summary_is_deterministic(self) -> None:
        from core.runtime.runtime_governance_closure import build_runtime_governance_closure_report

        first = build_runtime_governance_closure_report(governance_chain_seal_report=copy.deepcopy(self._valid_seal()))
        second = build_runtime_governance_closure_report(governance_chain_seal_report=copy.deepcopy(self._valid_seal()))

        self.assertEqual(first["governance_closure_id"], second["governance_closure_id"])
        self.assertEqual(first["closure_summary"], second["closure_summary"])

    def test_summary_builder(self) -> None:
        from core.runtime.runtime_governance_closure import (
            build_runtime_governance_closure_report,
            build_runtime_governance_closure_summary,
        )

        report = build_runtime_governance_closure_report(governance_chain_seal_report=self._valid_seal())
        summary = build_runtime_governance_closure_summary(report)

        self.assertTrue(summary["closure_ready"])
        self.assertEqual(summary["closure_state"], "closed")
        self.assertTrue(summary["runtime_governance_freeze_candidate"])
        self.assertEqual(summary["closure_blocker_count"], 0)


if __name__ == "__main__":
    unittest.main()
