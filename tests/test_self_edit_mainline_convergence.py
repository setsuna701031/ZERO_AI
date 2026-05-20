from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class SelfEditMainlineConvergenceTest(unittest.TestCase):
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

    def test_stage_and_report_contract_helpers_are_stable(self) -> None:
        from core.runtime.self_edit_mainline_convergence import (
            self_edit_convergence_required_fields,
            self_edit_mainline_stages,
        )

        self.assertEqual(
            self_edit_mainline_stages(),
            ["policy", "mutation", "verification", "rollback", "evidence", "landing"],
        )
        self.assertEqual(
            self_edit_convergence_required_fields(),
            [
                "convergence_id",
                "self_edit_flow_id",
                "convergence_state",
                "checked_stages",
                "missing_stages",
                "incompatible_fields",
                "evidence_refs",
                "landing_consistency",
                "continuation_recommendation",
                "cross_session_handoff_ready",
                "blocking_issues",
                "convergence_score",
                "reason_codes",
            ],
        )

    def test_collects_self_edit_mainline_contract_shape(self) -> None:
        from core.runtime.self_edit_mainline_convergence import (
            collect_self_edit_mainline_contract_shape,
            validate_self_edit_mainline_stages,
        )

        shape = collect_self_edit_mainline_contract_shape(self._flow())
        validation = validate_self_edit_mainline_stages(self._flow())

        self.assertEqual(shape["self_edit_flow_id"], "self-edit-1")
        self.assertEqual(shape["checked_stages"][0], "policy")
        self.assertTrue(shape["stages"]["landing"]["present"])
        self.assertEqual(shape["stages"]["landing"]["missing_fields"], [])
        self.assertTrue(validation["ok"])

    def test_converged_report_has_no_action_recommendation(self) -> None:
        from core.runtime.self_edit_mainline_convergence import (
            build_self_edit_convergence_report,
            validate_self_edit_convergence_report,
        )

        report = build_self_edit_convergence_report(
            self._flow(),
            forensic_report=self._forensic_report(),
        )
        validation = validate_self_edit_convergence_report(report)

        self.assertTrue(report["convergence_id"].startswith("self-edit-convergence-"))
        self.assertEqual(report["self_edit_flow_id"], "self-edit-1")
        self.assertEqual(report["convergence_state"], "converged")
        self.assertEqual(report["missing_stages"], [])
        self.assertEqual(report["incompatible_fields"], [])
        self.assertEqual(report["evidence_refs"]["evidence_ref"], "evidence-1")
        self.assertTrue(report["cross_session_handoff_ready"])
        self.assertEqual(report["next_action_recommendations"][0]["action_type"], "no_action")
        self.assertTrue(validation["ok"])

    def test_detects_missing_convergence_stages(self) -> None:
        from core.runtime.self_edit_mainline_convergence import (
            build_self_edit_convergence_report,
            detect_missing_convergence_stages,
        )

        flow = self._flow()
        del flow["verification"]

        report = build_self_edit_convergence_report(flow, forensic_report=self._forensic_report())

        self.assertEqual(detect_missing_convergence_stages(flow), ["verification"])
        self.assertEqual(report["convergence_state"], "needs_review")
        self.assertIn("verification", report["missing_stages"])
        self.assertIn("missing_convergence_stages", report["reason_codes"])

    def test_detects_incompatible_landing_fields_and_blocks(self) -> None:
        from core.runtime.self_edit_mainline_convergence import (
            build_self_edit_convergence_report,
            detect_incompatible_landing_fields,
        )

        flow = self._flow()
        flow["landing"]["status"] = {"state": "finished"}
        landing_report = {
            "self_edit": flow["landing"],
            "repair": {**flow["landing"], "status": "finished", "repair_chain_id": "repair-1"},
        }

        report = build_self_edit_convergence_report(
            flow,
            forensic_report=self._forensic_report(),
            landing_consistency_report=landing_report,
        )

        self.assertEqual(detect_incompatible_landing_fields(landing_report)[0]["field"], "status")
        self.assertEqual(report["convergence_state"], "blocked")
        self.assertEqual(report["incompatible_fields"][0]["field"], "status")
        self.assertIn("landing_incompatible_fields", report["reason_codes"])

    def test_detects_missing_forensic_and_evidence_refs(self) -> None:
        from core.runtime.self_edit_mainline_convergence import (
            build_self_edit_convergence_report,
            detect_missing_forensic_evidence_refs,
        )

        flow = self._flow()
        del flow["evidence"]["evidence_ref"]
        del flow["landing"]["evidence_ref"]
        del flow["landing"]["audit_ref"]

        missing = detect_missing_forensic_evidence_refs(flow, forensic_report={})
        report = build_self_edit_convergence_report(flow, forensic_report={})

        self.assertEqual(
            [item["kind"] for item in missing],
            [
                "missing_evidence_ref",
                "missing_audit_ref",
                "missing_forensic_report_id",
                "missing_forensic_source_records",
            ],
        )
        self.assertEqual(report["convergence_state"], "blocked")
        self.assertIn("missing_evidence_ref", report["reason_codes"])
        self.assertIn("missing_audit_ref", report["reason_codes"])

    def test_continuation_recommendation_can_make_report_need_review(self) -> None:
        from core.runtime.autonomous_continuation_policy import (
            build_autonomous_continuation_recommendation,
        )
        from core.runtime.self_edit_mainline_convergence import (
            build_self_edit_convergence_report,
        )

        forensic = self._forensic_report(broken=True)
        continuation = build_autonomous_continuation_recommendation(forensic)

        report = build_self_edit_convergence_report(
            self._flow(),
            forensic_report=forensic,
            continuation_recommendation=continuation,
        )

        self.assertEqual(report["convergence_state"], "needs_review")
        self.assertTrue(report["cross_session_handoff_ready"])
        self.assertIn("parent_session_id_not_found", report["reason_codes"])
        self.assertIn(
            "repair_recommended",
            [item["action_type"] for item in report["next_action_recommendations"]],
        )

    def test_validate_self_edit_convergence_report_shape(self) -> None:
        from core.runtime.self_edit_mainline_convergence import (
            validate_self_edit_convergence_report,
        )

        invalid = validate_self_edit_convergence_report(
            {
                "convergence_id": "convergence-1",
                "self_edit_flow_id": "self-edit-1",
                "convergence_state": "almost",
                "checked_stages": {},
                "missing_stages": [],
                "incompatible_fields": [],
                "evidence_refs": {},
                "landing_consistency": {},
                "continuation_recommendation": {},
                "cross_session_handoff_ready": False,
                "blocking_issues": [],
                "convergence_score": 0,
                "reason_codes": [],
            }
        )
        missing = validate_self_edit_convergence_report({})

        self.assertFalse(invalid["ok"])
        self.assertEqual(
            [item["field"] for item in invalid["invalid_fields"]],
            ["convergence_state", "checked_stages"],
        )
        self.assertFalse(missing["ok"])
        self.assertIn("convergence_id", missing["missing_fields"])

    def test_builder_is_stable_and_does_not_mutate_inputs(self) -> None:
        from core.runtime.self_edit_mainline_convergence import (
            build_self_edit_convergence_report,
        )

        flow = self._flow()
        forensic = self._forensic_report(broken=True)
        flow_before = copy.deepcopy(flow)
        forensic_before = copy.deepcopy(forensic)

        first = build_self_edit_convergence_report(flow, forensic_report=forensic)
        second = build_self_edit_convergence_report(flow, forensic_report=forensic)

        self.assertEqual(first, second)
        self.assertEqual(flow, flow_before)
        self.assertEqual(forensic, forensic_before)


if __name__ == "__main__":
    unittest.main()
