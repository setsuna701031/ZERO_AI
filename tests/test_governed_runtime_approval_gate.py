from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class GovernedRuntimeApprovalGateTest(unittest.TestCase):
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

    def _dry_run(self, *, broken: bool = True, approval_required: bool = False, dry_run_only: bool = True) -> dict:
        from core.runtime.governance_transition_readiness import (
            build_governance_transition_readiness_report,
        )
        from core.runtime.governed_runtime_action_gateway import (
            build_governed_action_request_gateway_report,
        )
        from core.runtime.governed_runtime_dry_run_executor import (
            build_governed_runtime_dry_run_report,
        )

        forensic = self._forensic_report(broken=broken)
        readiness = build_governance_transition_readiness_report(
            forensic_report=forensic,
            self_edit_flow=self._flow(),
            windows_runtime_report=self._windows_ready(),
        )
        gateway = build_governed_action_request_gateway_report(
            readiness_report=readiness,
            forensic_report=forensic,
            approval_required=approval_required,
            dry_run_only=dry_run_only,
        )
        return build_governed_runtime_dry_run_report(gateway_report=gateway)

    def test_required_fields_are_stable(self) -> None:
        from core.runtime.governed_runtime_approval_gate import (
            governed_runtime_approval_gate_required_fields,
        )

        self.assertEqual(
            governed_runtime_approval_gate_required_fields(),
            [
                "approval_gate_id",
                "source_dry_run_id",
                "approval_state",
                "execution_eligible",
                "approval_required",
                "unresolved_approval_actions",
                "evidence_refs",
                "seal_refs",
                "affected_repair_chain_ids",
                "blocking_issues",
                "reason_codes",
            ],
        )

    def test_approved_when_dry_run_completed_with_refs(self) -> None:
        from core.runtime.governed_runtime_approval_gate import (
            build_governed_runtime_approval_gate_report,
            validate_governed_runtime_approval_gate_report,
        )

        dry_run = self._dry_run(broken=True)

        report = build_governed_runtime_approval_gate_report(dry_run_report=dry_run)
        validation = validate_governed_runtime_approval_gate_report(report)

        self.assertTrue(report["approval_gate_id"].startswith("governed-runtime-approval-gate-"))
        self.assertEqual(report["source_dry_run_id"], dry_run["dry_run_id"])
        self.assertEqual(report["approval_state"], "approved")
        self.assertTrue(report["execution_eligible"])
        self.assertFalse(report["approval_required"])
        self.assertEqual(report["unresolved_approval_actions"], [])
        self.assertEqual(report["evidence_refs"], dry_run["evidence_refs"])
        self.assertEqual(report["seal_refs"], dry_run["seal_refs"])
        self.assertEqual(report["affected_repair_chain_ids"], ["repair-1"])
        self.assertTrue(validation["ok"])

    def test_blocks_when_dry_run_blocked(self) -> None:
        from core.runtime.governed_runtime_approval_gate import (
            build_governed_runtime_approval_gate_report,
            validate_dry_run_before_approval,
        )

        dry_run = self._dry_run(broken=True)
        dry_run["dry_run_state"] = "blocked"
        dry_run["blocking_issues"] = [{"kind": "execute_true_not_allowed"}]

        validation = validate_dry_run_before_approval(dry_run)
        report = build_governed_runtime_approval_gate_report(dry_run_report=dry_run)

        self.assertFalse(validation["ok"])
        self.assertEqual(report["approval_state"], "blocked")
        self.assertFalse(report["execution_eligible"])
        self.assertIn("dry_run_blocked", report["reason_codes"])

    def test_blocks_when_evidence_or_seal_refs_missing(self) -> None:
        from core.runtime.governed_runtime_approval_gate import (
            build_governed_runtime_approval_gate_report,
        )

        dry_run = self._dry_run(broken=True)
        dry_run["evidence_refs"] = {}
        dry_run["seal_refs"] = {}

        report = build_governed_runtime_approval_gate_report(dry_run_report=dry_run)

        self.assertEqual(report["approval_state"], "blocked")
        self.assertIn("missing_evidence_refs", report["reason_codes"])
        self.assertIn("missing_seal_refs", report["reason_codes"])

    def test_unresolved_approval_actions_need_review(self) -> None:
        from core.runtime.governed_runtime_approval_gate import (
            build_controlled_execution_eligibility_summary,
            build_governed_runtime_approval_gate_report,
            unresolved_approval_actions,
        )

        dry_run = self._dry_run(broken=True, approval_required=True, dry_run_only=False)

        report = build_governed_runtime_approval_gate_report(dry_run_report=dry_run)
        summary = build_controlled_execution_eligibility_summary(report)

        self.assertEqual(report["approval_state"], "needs_review")
        self.assertFalse(report["execution_eligible"])
        self.assertTrue(report["approval_required"])
        self.assertEqual(unresolved_approval_actions(dry_run), dry_run["approval_required_actions"])
        self.assertEqual(summary["unresolved_approval_action_count"], 1)
        self.assertFalse(summary["execute"])
        self.assertFalse(summary["planner_invoked"])
        self.assertFalse(summary["task_enqueued"])

    def test_builds_gate_from_source_inputs(self) -> None:
        from core.runtime.governed_runtime_approval_gate import (
            build_governed_runtime_approval_gate_report,
        )

        report = build_governed_runtime_approval_gate_report(
            forensic_report=self._forensic_report(broken=True),
        )

        self.assertTrue(report["source_dry_run_id"])
        self.assertIn(report["approval_state"], ["approved", "needs_review", "blocked"])
        self.assertIn("controlled_execution_eligibility", report)

    def test_validate_approval_gate_report_shape(self) -> None:
        from core.runtime.governed_runtime_approval_gate import (
            validate_governed_runtime_approval_gate_report,
        )

        invalid = validate_governed_runtime_approval_gate_report(
            {
                "approval_gate_id": "gate-1",
                "source_dry_run_id": "dry-run-1",
                "approval_state": "maybe",
                "execution_eligible": False,
                "approval_required": False,
                "unresolved_approval_actions": {},
                "evidence_refs": {},
                "seal_refs": {},
                "affected_repair_chain_ids": [],
                "blocking_issues": [],
                "reason_codes": [],
            }
        )
        missing = validate_governed_runtime_approval_gate_report({})

        self.assertFalse(invalid["ok"])
        self.assertEqual(
            [item["field"] for item in invalid["invalid_fields"]],
            ["approval_state", "unresolved_approval_actions"],
        )
        self.assertFalse(missing["ok"])
        self.assertIn("approval_gate_id", missing["missing_fields"])

    def test_gate_builder_is_stable_and_does_not_mutate_inputs(self) -> None:
        from core.runtime.governed_runtime_approval_gate import (
            build_governed_runtime_approval_gate_report,
        )

        dry_run = self._dry_run(broken=True)
        before = copy.deepcopy(dry_run)

        first = build_governed_runtime_approval_gate_report(dry_run_report=dry_run)
        second = build_governed_runtime_approval_gate_report(dry_run_report=dry_run)

        self.assertEqual(first, second)
        self.assertEqual(dry_run, before)


if __name__ == "__main__":
    unittest.main()
