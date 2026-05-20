from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeGovernanceClosureTest(unittest.TestCase):
    def _flow(self) -> dict:
        landing = {
            "task_id": "self-edit-task",
            "session_id": "session-1",
            "status": "finished",
            "execution_result": {"ok": True},
            "verification_result": {"ok": True},
            "rollback_result": {"needed": False},
            "audit_ref": "audit-1",
            "evidence_ref": "evidence-1",
            "mutation_ref": "mutation-1",
        }
        return {
            "self_edit_flow_id": "self-edit-1",
            "policy": {"policy_id": "policy-1", "decision": "allow"},
            "mutation": {"mutation_ref": "mutation-1", "status": "applied"},
            "verification": {"verification_result": {"ok": True}},
            "rollback": {"rollback_result": {"needed": False}},
            "evidence": {"evidence_ref": "evidence-1"},
            "landing": landing,
        }

    def _records(self, *, broken: bool = False) -> list[dict]:
        root = {
            "status": "finished",
            "engineering_continuity": {
                "session_id": "root",
                "execution_chain_depth": 0,
                "previous_runtime_state_ref": "state-root",
            },
        }
        child = {
            "status": "finished",
            "engineering_continuity": {
                "session_id": "child",
                "parent_session_id": "root",
                "execution_chain_depth": 1,
                "previous_runtime_state_ref": "state-child",
            },
        }
        if broken:
            child["engineering_continuity"]["parent_session_id"] = "missing-parent"
            child["engineering_continuity"]["repair_chain_id"] = "repair-1"
        return [root, child]

    def _forensic_report(self, *, broken: bool = False) -> dict:
        from core.runtime.runtime_forensic_stack import build_runtime_forensic_report

        return build_runtime_forensic_report(self._records(broken=broken))

    def test_closure_constants_are_stable(self) -> None:
        from core.runtime.runtime_governance_closure import (
            runtime_governance_closure_layers,
            runtime_governance_closure_required_fields,
        )

        self.assertEqual(
            runtime_governance_closure_layers(),
            [
                "forensic_stack",
                "evidence_bundle",
                "replay_snapshot_seal",
                "autonomous_continuation",
                "cross_session_continuity",
                "self_edit_convergence",
                "execution_landing_consistency",
            ],
        )
        self.assertEqual(
            runtime_governance_closure_required_fields(),
            [
                "closure_id",
                "closure_state",
                "forensic_ready",
                "evidence_ready",
                "seal_ready",
                "continuation_ready",
                "cross_session_ready",
                "self_edit_converged",
                "landing_consistent",
                "governance_blockers",
                "recommended_actions",
                "affected_repair_chain_ids",
                "audit_summary",
                "closure_score",
                "reason_codes",
            ],
        )

    def test_builds_closed_governance_closure_report(self) -> None:
        from core.runtime.runtime_governance_closure import (
            build_runtime_governance_closure_report,
            validate_runtime_governance_closure_report,
        )

        report = build_runtime_governance_closure_report(
            forensic_report=self._forensic_report(),
            self_edit_flow=self._flow(),
        )
        validation = validate_runtime_governance_closure_report(report)

        self.assertTrue(report["closure_id"].startswith("runtime-governance-closure-"))
        self.assertEqual(report["closure_state"], "closed")
        self.assertTrue(report["forensic_ready"])
        self.assertTrue(report["evidence_ready"])
        self.assertTrue(report["seal_ready"])
        self.assertTrue(report["continuation_ready"])
        self.assertTrue(report["cross_session_ready"])
        self.assertTrue(report["self_edit_converged"])
        self.assertTrue(report["landing_consistent"])
        self.assertEqual(report["governance_blockers"], [])
        self.assertEqual(report["recommended_actions"][0]["action_type"], "no_action")
        self.assertFalse(report["audit_summary"]["audit_log_written"])
        self.assertTrue(validation["ok"])

    def test_checks_alignment_and_audit_summary(self) -> None:
        from core.runtime.autonomous_continuation_policy import (
            build_autonomous_continuation_recommendation,
        )
        from core.runtime.cross_session_engineering_continuity import (
            build_cross_session_handoff_payload,
        )
        from core.runtime.runtime_governance_closure import (
            build_audit_ready_closure_summary,
            check_runtime_governance_alignment,
        )
        from core.runtime.runtime_replay_snapshot_seal import (
            seal_replay_reconstruction_report,
        )
        from core.runtime.self_edit_mainline_convergence import (
            build_self_edit_convergence_report,
        )

        forensic = self._forensic_report()
        continuation = build_autonomous_continuation_recommendation(forensic)
        handoff = build_cross_session_handoff_payload(
            forensic_report=forensic,
            continuation_recommendation=continuation,
        )
        convergence = build_self_edit_convergence_report(
            self._flow(),
            forensic_report=forensic,
            continuation_recommendation=continuation,
        )
        seal = seal_replay_reconstruction_report(forensic["reconstruction_report"])
        landing = convergence["landing_consistency"]

        alignment = check_runtime_governance_alignment(
            forensic_report=forensic,
            continuation_recommendation=continuation,
            cross_session_handoff=handoff,
            convergence_report=convergence,
            landing_consistency_report=landing,
            snapshot_seal=seal,
        )
        summary = build_audit_ready_closure_summary(
            {
                "closure_id": "closure-1",
                "closure_state": "closed",
                **alignment,
                "governance_blockers": [],
                "recommended_actions": [{"action_type": "no_action"}],
                "affected_repair_chain_ids": [],
                "closure_score": 1.0,
                "reason_codes": [],
            }
        )

        self.assertTrue(alignment["forensic_ready"])
        self.assertTrue(alignment["seal_ready"])
        self.assertEqual(alignment["forensic_report_id"], forensic["report_id"])
        self.assertEqual(summary["closure_id"], "closure-1")
        self.assertFalse(summary["audit_log_written"])

    def test_missing_layers_produce_needs_review_actions(self) -> None:
        from core.runtime.runtime_governance_closure import (
            build_runtime_governance_closure_report,
            detect_missing_closure_layers,
        )

        forensic = self._forensic_report()

        missing = detect_missing_closure_layers(forensic_report=forensic)
        report = build_runtime_governance_closure_report(forensic_report=forensic)

        self.assertIn("autonomous_continuation", missing)
        self.assertIn("self_edit_convergence", report["missing_layers"])
        self.assertEqual(report["closure_state"], "needs_review")
        self.assertIn("missing_closure_layers", report["reason_codes"])
        self.assertIn(
            "needs_review",
            [item["action_type"] for item in report["recommended_actions"]],
        )

    def test_landing_inconsistency_blocks_closure(self) -> None:
        from core.runtime.runtime_governance_closure import (
            build_runtime_governance_closure_report,
        )

        flow = self._flow()
        landing = {
            "self_edit": {**flow["landing"], "status": {"state": "finished"}},
            "repair": {**flow["landing"], "status": "finished", "repair_chain_id": "repair-1"},
        }

        report = build_runtime_governance_closure_report(
            forensic_report=self._forensic_report(),
            self_edit_flow=flow,
            landing_consistency_report=landing,
        )

        self.assertEqual(report["closure_state"], "blocked")
        self.assertFalse(report["landing_consistent"])
        self.assertIn("incompatible_field", report["reason_codes"])
        self.assertIn(
            "blocked",
            [item["action_type"] for item in report["recommended_actions"]],
        )

    def test_needs_review_continuation_preserves_repair_chains(self) -> None:
        from core.runtime.runtime_governance_closure import (
            build_runtime_governance_closure_report,
        )

        report = build_runtime_governance_closure_report(
            forensic_report=self._forensic_report(broken=True),
            self_edit_flow=self._flow(),
        )

        self.assertEqual(report["closure_state"], "needs_review")
        self.assertEqual(report["affected_repair_chain_ids"], ["repair-1"])
        self.assertIn("parent_session_id_not_found", report["reason_codes"])

    def test_bad_seal_blocks_closure(self) -> None:
        from core.runtime.runtime_governance_closure import (
            build_runtime_governance_closure_report,
        )

        report = build_runtime_governance_closure_report(
            forensic_report=self._forensic_report(),
            self_edit_flow=self._flow(),
            snapshot_seal={
                "seal_version": "runtime_replay_snapshot_seal.v1",
                "snapshot_seal_id": "seal-bad",
                "report_id": "other-report",
                "replay_hash": "r",
                "integrity_hash": "i",
                "divergence_hash": "d",
                "repair_chain_ids": [],
                "source_record_count": 2,
            },
        )

        self.assertEqual(report["closure_state"], "blocked")
        self.assertFalse(report["seal_ready"])
        self.assertIn("layer_not_ready", report["reason_codes"])

    def test_validate_runtime_governance_closure_report_shape(self) -> None:
        from core.runtime.runtime_governance_closure import (
            validate_runtime_governance_closure_report,
        )

        invalid = validate_runtime_governance_closure_report(
            {
                "closure_id": "closure-1",
                "closure_state": "almost",
                "forensic_ready": True,
                "evidence_ready": True,
                "seal_ready": True,
                "continuation_ready": True,
                "cross_session_ready": True,
                "self_edit_converged": True,
                "landing_consistent": True,
                "governance_blockers": {},
                "recommended_actions": [],
                "affected_repair_chain_ids": [],
                "audit_summary": {},
                "closure_score": 1.0,
                "reason_codes": [],
            }
        )
        missing = validate_runtime_governance_closure_report({})

        self.assertFalse(invalid["ok"])
        self.assertEqual(
            [item["field"] for item in invalid["invalid_fields"]],
            ["closure_state", "governance_blockers"],
        )
        self.assertFalse(missing["ok"])
        self.assertIn("closure_id", missing["missing_fields"])

    def test_builder_is_stable_and_does_not_mutate_inputs(self) -> None:
        from core.runtime.runtime_governance_closure import (
            build_runtime_governance_closure_report,
        )

        forensic = self._forensic_report(broken=True)
        flow = self._flow()
        forensic_before = copy.deepcopy(forensic)
        flow_before = copy.deepcopy(flow)

        first = build_runtime_governance_closure_report(
            forensic_report=forensic,
            self_edit_flow=flow,
        )
        second = build_runtime_governance_closure_report(
            forensic_report=forensic,
            self_edit_flow=flow,
        )

        self.assertEqual(first, second)
        self.assertEqual(forensic, forensic_before)
        self.assertEqual(flow, flow_before)


if __name__ == "__main__":
    unittest.main()
