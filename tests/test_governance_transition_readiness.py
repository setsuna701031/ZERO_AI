from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class GovernanceTransitionReadinessTest(unittest.TestCase):
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

    def _windows_ready(self) -> dict:
        return {
            "schema_version": "windows_runtime_stabilization.v1",
            "report_id": "windows-ready",
            "launcher_valid": True,
            "base_interpreter_missing": False,
            "bundled_python_detected": True,
            "bundled_python_inconsistent": False,
            "circular_reference_risk": False,
            "smoke_blockers": [],
            "json_safe": True,
            "runtime_environment_score": 1.0,
            "blocking_issues": [],
            "details": {},
        }

    def test_required_fields_are_stable(self) -> None:
        from core.runtime.governance_transition_readiness import (
            governance_transition_readiness_required_fields,
        )

        self.assertEqual(
            governance_transition_readiness_required_fields(),
            [
                "readiness_id",
                "transition_state",
                "governance_closed",
                "self_edit_ready",
                "continuation_ready",
                "cross_session_ready",
                "landing_ready",
                "seal_ready",
                "windows_runtime_ready",
                "blocking_issues",
                "recommended_actions",
                "readiness_score",
                "reason_codes",
            ],
        )

    def test_builds_ready_transition_report(self) -> None:
        from core.runtime.governance_transition_readiness import (
            build_governance_transition_readiness_report,
            validate_governance_transition_readiness_report,
        )

        report = build_governance_transition_readiness_report(
            forensic_report=self._forensic_report(),
            self_edit_flow=self._flow(),
            windows_runtime_report=self._windows_ready(),
        )
        validation = validate_governance_transition_readiness_report(report)

        self.assertTrue(report["readiness_id"].startswith("governance-transition-readiness-"))
        self.assertEqual(report["transition_state"], "ready")
        self.assertTrue(report["governance_closed"])
        self.assertTrue(report["self_edit_ready"])
        self.assertTrue(report["continuation_ready"])
        self.assertTrue(report["cross_session_ready"])
        self.assertTrue(report["landing_ready"])
        self.assertTrue(report["seal_ready"])
        self.assertTrue(report["windows_runtime_ready"])
        self.assertEqual(report["blocking_issues"], [])
        self.assertEqual(report["recommended_actions"][0]["action_type"], "no_action")
        self.assertTrue(validation["ok"])

    def test_component_check_helpers_accept_usable_reports(self) -> None:
        from core.runtime.autonomous_continuation_policy import (
            build_autonomous_continuation_recommendation,
        )
        from core.runtime.cross_session_engineering_continuity import (
            build_cross_session_handoff_payload,
        )
        from core.runtime.governance_transition_readiness import (
            check_continuation_policy_usable,
            check_cross_session_handoff_usable,
            check_execution_landing_consistent,
            check_governance_closure_usable,
            check_replay_snapshot_seal_usable,
            check_self_edit_convergence_usable,
            check_windows_runtime_blockers,
        )
        from core.runtime.runtime_governance_closure import (
            build_runtime_governance_closure_report,
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
        closure = build_runtime_governance_closure_report(
            forensic_report=forensic,
            self_edit_flow=self._flow(),
            continuation_recommendation=continuation,
            cross_session_handoff=handoff,
            convergence_report=convergence,
        )
        seal = seal_replay_reconstruction_report(forensic["reconstruction_report"])

        self.assertTrue(check_governance_closure_usable(closure)["usable"])
        self.assertTrue(check_self_edit_convergence_usable(convergence)["usable"])
        self.assertTrue(check_continuation_policy_usable(continuation)["usable"])
        self.assertTrue(check_cross_session_handoff_usable(handoff)["usable"])
        self.assertTrue(check_execution_landing_consistent(convergence["landing_consistency"])["usable"])
        self.assertTrue(check_replay_snapshot_seal_usable(seal, forensic_report=forensic)["usable"])
        self.assertTrue(check_windows_runtime_blockers(self._windows_ready())["usable"])

    def test_windows_runtime_blocker_blocks_transition(self) -> None:
        from core.runtime.governance_transition_readiness import (
            build_governance_transition_readiness_report,
        )

        windows = self._windows_ready()
        windows["blocking_issues"] = [{"kind": "base_interpreter_missing", "path": "C:\\missing\\python.exe"}]

        report = build_governance_transition_readiness_report(
            forensic_report=self._forensic_report(),
            self_edit_flow=self._flow(),
            windows_runtime_report=windows,
        )

        self.assertEqual(report["transition_state"], "blocked")
        self.assertFalse(report["windows_runtime_ready"])
        self.assertIn("base_interpreter_missing", report["reason_codes"])
        self.assertEqual(report["recommended_actions"][0]["action_type"], "blocked")

    def test_governance_not_closed_blocks_transition(self) -> None:
        from core.runtime.governance_transition_readiness import (
            build_governance_transition_readiness_report,
        )

        report = build_governance_transition_readiness_report(
            governance_closure_report={
                "closure_id": "closure-1",
                "closure_state": "blocked",
                "forensic_ready": True,
                "evidence_ready": True,
                "seal_ready": True,
                "continuation_ready": False,
                "cross_session_ready": False,
                "self_edit_converged": False,
                "landing_consistent": True,
                "governance_blockers": [{"kind": "continuation_blocked"}],
                "recommended_actions": [],
                "affected_repair_chain_ids": [],
                "audit_summary": {},
                "closure_score": 0.5,
                "reason_codes": ["continuation_blocked"],
            },
            self_edit_convergence_report={},
            continuation_recommendation={},
            cross_session_handoff={},
            landing_consistency_report={},
            snapshot_seal={},
            windows_runtime_report=self._windows_ready(),
        )

        self.assertEqual(report["transition_state"], "blocked")
        self.assertFalse(report["governance_closed"])
        self.assertIn("continuation_blocked", report["reason_codes"])

    def test_needs_review_when_optional_reports_missing_but_no_hard_blocker(self) -> None:
        from core.runtime.governance_transition_readiness import (
            build_governance_transition_readiness_report,
        )

        report = build_governance_transition_readiness_report(
            continuation_recommendation={
                "policy_id": "autonomous_continuation_policy.v1",
                "input_report_id": "report-1",
                "continuation_state": "safe_to_continue",
                "recommended_actions": [],
                "blocking_issues": [],
                "affected_repair_chain_ids": [],
                "planner_handoff_payload": {},
                "confidence": 1.0,
                "reason_codes": [],
            },
            cross_session_handoff={
                "handoff_id": "handoff-1",
                "source_session_id": "session-1",
                "source_report_id": "report-1",
                "continuation_state": "safe_to_continue",
                "recommended_actions": [],
                "blocking_issues": [],
                "affected_repair_chain_ids": [],
                "next_session_startup_hints": [],
                "planner_handoff_payload": {},
                "handoff_valid": True,
                "reason_codes": [],
            },
            windows_runtime_report=self._windows_ready(),
        )

        self.assertEqual(report["transition_state"], "needs_review")
        self.assertTrue(report["continuation_ready"])
        self.assertTrue(report["cross_session_ready"])
        self.assertEqual(report["recommended_actions"][0]["action_type"], "needs_review")

    def test_landing_inconsistency_blocks_transition(self) -> None:
        from core.runtime.governance_transition_readiness import (
            build_governance_transition_readiness_report,
        )

        flow = self._flow()
        landing = {
            "self_edit": {**flow["landing"], "status": {"state": "finished"}},
            "repair": {**flow["landing"], "status": "finished", "repair_chain_id": "repair-1"},
        }

        report = build_governance_transition_readiness_report(
            forensic_report=self._forensic_report(),
            self_edit_flow=flow,
            landing_consistency_report=landing,
            windows_runtime_report=self._windows_ready(),
        )

        self.assertEqual(report["transition_state"], "blocked")
        self.assertFalse(report["landing_ready"])
        self.assertIn("incompatible_field", report["reason_codes"])

    def test_bad_snapshot_seal_blocks_transition(self) -> None:
        from core.runtime.governance_transition_readiness import (
            build_governance_transition_readiness_report,
        )

        report = build_governance_transition_readiness_report(
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
            windows_runtime_report=self._windows_ready(),
        )

        self.assertEqual(report["transition_state"], "blocked")
        self.assertFalse(report["seal_ready"])
        self.assertIn("replay_snapshot_seal_not_usable", report["reason_codes"])

    def test_validate_governance_transition_readiness_report_shape(self) -> None:
        from core.runtime.governance_transition_readiness import (
            validate_governance_transition_readiness_report,
        )

        invalid = validate_governance_transition_readiness_report(
            {
                "readiness_id": "ready-1",
                "transition_state": "almost",
                "governance_closed": True,
                "self_edit_ready": True,
                "continuation_ready": True,
                "cross_session_ready": True,
                "landing_ready": True,
                "seal_ready": True,
                "windows_runtime_ready": True,
                "blocking_issues": {},
                "recommended_actions": [],
                "readiness_score": 1.0,
                "reason_codes": [],
            }
        )
        missing = validate_governance_transition_readiness_report({})

        self.assertFalse(invalid["ok"])
        self.assertEqual(
            [item["field"] for item in invalid["invalid_fields"]],
            ["transition_state", "blocking_issues"],
        )
        self.assertFalse(missing["ok"])
        self.assertIn("readiness_id", missing["missing_fields"])

    def test_builder_is_stable_and_does_not_mutate_inputs(self) -> None:
        from core.runtime.governance_transition_readiness import (
            build_governance_transition_readiness_report,
        )

        forensic = self._forensic_report(broken=True)
        flow = self._flow()
        windows = self._windows_ready()
        forensic_before = copy.deepcopy(forensic)
        flow_before = copy.deepcopy(flow)
        windows_before = copy.deepcopy(windows)

        first = build_governance_transition_readiness_report(
            forensic_report=forensic,
            self_edit_flow=flow,
            windows_runtime_report=windows,
        )
        second = build_governance_transition_readiness_report(
            forensic_report=forensic,
            self_edit_flow=flow,
            windows_runtime_report=windows,
        )

        self.assertEqual(first, second)
        self.assertEqual(forensic, forensic_before)
        self.assertEqual(flow, flow_before)
        self.assertEqual(windows, windows_before)


if __name__ == "__main__":
    unittest.main()
