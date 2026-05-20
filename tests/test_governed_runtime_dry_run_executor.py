from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class GovernedRuntimeDryRunExecutorTest(unittest.TestCase):
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

    def _gateway(self, *, broken: bool = True, approval_required: bool = False, dry_run_only: bool = True) -> dict:
        from core.runtime.governance_transition_readiness import (
            build_governance_transition_readiness_report,
        )
        from core.runtime.governed_runtime_action_gateway import (
            build_governed_action_request_gateway_report,
        )

        forensic = self._forensic_report(broken=broken)
        readiness = build_governance_transition_readiness_report(
            forensic_report=forensic,
            self_edit_flow=self._flow(),
            windows_runtime_report=self._windows_ready(),
        )
        return build_governed_action_request_gateway_report(
            readiness_report=readiness,
            forensic_report=forensic,
            approval_required=approval_required,
            dry_run_only=dry_run_only,
        )

    def test_required_fields_are_stable(self) -> None:
        from core.runtime.governed_runtime_dry_run_executor import (
            governed_runtime_dry_run_required_fields,
        )

        self.assertEqual(
            governed_runtime_dry_run_required_fields(),
            [
                "dry_run_id",
                "source_gateway_id",
                "dry_run_state",
                "simulated_actions",
                "rejected_actions",
                "approval_required_actions",
                "evidence_refs",
                "seal_refs",
                "affected_repair_chain_ids",
                "blocking_issues",
                "reason_codes",
            ],
        )

    def test_validates_governed_action_requests(self) -> None:
        from core.runtime.governed_runtime_dry_run_executor import (
            validate_governed_action_request,
        )

        request = self._gateway()["action_requests"][0]
        invalid = validate_governed_action_request({"request_type": "execute_now"})

        self.assertTrue(validate_governed_action_request(request)["ok"])
        self.assertFalse(invalid["ok"])
        self.assertIn("request_id", invalid["missing_fields"])

    def test_simulates_dry_run_repair_request_without_execution(self) -> None:
        from core.runtime.governed_runtime_dry_run_executor import (
            build_governed_runtime_dry_run_report,
            validate_governed_runtime_dry_run_report,
        )

        gateway = self._gateway(broken=True)

        report = build_governed_runtime_dry_run_report(gateway_report=gateway)
        validation = validate_governed_runtime_dry_run_report(report)

        self.assertTrue(report["dry_run_id"].startswith("governed-runtime-dry-run-"))
        self.assertEqual(report["source_gateway_id"], gateway["gateway_id"])
        self.assertEqual(report["dry_run_state"], "dry_run_completed")
        self.assertEqual(report["simulated_actions"][0]["simulation_type"], "repair_dry_run_simulation")
        self.assertFalse(report["simulated_actions"][0]["execute"])
        self.assertFalse(report["simulated_actions"][0]["planner_invoked"])
        self.assertFalse(report["simulated_actions"][0]["task_enqueued"])
        self.assertEqual(report["affected_repair_chain_ids"], ["repair-1"])
        self.assertEqual(report["evidence_refs"], gateway["evidence_refs"])
        self.assertEqual(report["seal_refs"], gateway["seal_refs"])
        self.assertTrue(validation["ok"])

    def test_rejects_non_dry_run_execution_requests(self) -> None:
        from core.runtime.governed_runtime_dry_run_executor import (
            build_governed_runtime_dry_run_report,
            reject_non_dry_run_execution_requests,
        )

        request = copy.deepcopy(self._gateway()["action_requests"][0])
        request["execute"] = True
        request["dry_run_only"] = False

        rejected = reject_non_dry_run_execution_requests([request])
        report = build_governed_runtime_dry_run_report(action_requests=[request])

        self.assertIn("execute_true_not_allowed", rejected[0]["rejection_reasons"])
        self.assertIn("non_dry_run_request", rejected[0]["rejection_reasons"])
        self.assertEqual(report["dry_run_state"], "blocked")
        self.assertEqual(report["simulated_actions"], [])
        self.assertIn("execute_true_not_allowed", report["reason_codes"])

    def test_summarizes_approval_required_actions_without_approval_flow(self) -> None:
        from core.runtime.governed_runtime_dry_run_executor import (
            build_governed_runtime_dry_run_report,
            summarize_approval_required_actions,
        )

        gateway = self._gateway(broken=True, approval_required=True, dry_run_only=False)
        summaries = summarize_approval_required_actions(gateway["action_requests"])
        report = build_governed_runtime_dry_run_report(gateway_report=gateway)

        self.assertEqual(summaries[0]["approval_required"], True)
        self.assertFalse(summaries[0]["approval_flow_invoked"])
        self.assertEqual(report["dry_run_state"], "needs_review")
        self.assertEqual(report["simulated_actions"], [])
        self.assertEqual(report["approval_required_actions"][0]["request_type"], "approval_required_repair")

    def test_blocked_gateway_request_blocks_dry_run(self) -> None:
        from core.runtime.governance_transition_readiness import (
            build_governance_transition_readiness_report,
        )
        from core.runtime.governed_runtime_action_gateway import (
            build_governed_action_request_gateway_report,
        )
        from core.runtime.governed_runtime_dry_run_executor import (
            build_governed_runtime_dry_run_report,
        )

        windows = self._windows_ready()
        windows["blocking_issues"] = [{"kind": "base_interpreter_missing", "path": "C:\\missing\\python.exe"}]
        forensic = self._forensic_report()
        readiness = build_governance_transition_readiness_report(
            forensic_report=forensic,
            self_edit_flow=self._flow(),
            windows_runtime_report=windows,
        )
        gateway = build_governed_action_request_gateway_report(readiness_report=readiness)

        report = build_governed_runtime_dry_run_report(gateway_report=gateway)

        self.assertEqual(report["dry_run_state"], "blocked")
        self.assertEqual(report["rejected_actions"][0]["request_type"], "blocked")
        self.assertIn("blocked_request", report["reason_codes"])

    def test_builds_report_from_source_inputs(self) -> None:
        from core.runtime.governed_runtime_dry_run_executor import (
            build_governed_runtime_dry_run_report,
        )

        report = build_governed_runtime_dry_run_report(
            forensic_report=self._forensic_report(broken=True),
        )

        self.assertTrue(report["source_gateway_id"])
        self.assertIn(report["dry_run_state"], ["dry_run_completed", "blocked", "needs_review"])
        self.assertTrue(report["seal_refs"])

    def test_validate_dry_run_report_shape(self) -> None:
        from core.runtime.governed_runtime_dry_run_executor import (
            validate_governed_runtime_dry_run_report,
        )

        invalid = validate_governed_runtime_dry_run_report(
            {
                "dry_run_id": "dry-run-1",
                "source_gateway_id": "gateway-1",
                "dry_run_state": "executed",
                "simulated_actions": {},
                "rejected_actions": [],
                "approval_required_actions": [],
                "evidence_refs": {},
                "seal_refs": {},
                "affected_repair_chain_ids": [],
                "blocking_issues": [],
                "reason_codes": [],
            }
        )
        missing = validate_governed_runtime_dry_run_report({})

        self.assertFalse(invalid["ok"])
        self.assertEqual(
            [item["field"] for item in invalid["invalid_fields"]],
            ["dry_run_state", "simulated_actions"],
        )
        self.assertFalse(missing["ok"])
        self.assertIn("dry_run_id", missing["missing_fields"])

    def test_dry_run_builder_is_stable_and_does_not_mutate_inputs(self) -> None:
        from core.runtime.governed_runtime_dry_run_executor import (
            build_governed_runtime_dry_run_report,
        )

        gateway = self._gateway(broken=True)
        before = copy.deepcopy(gateway)

        first = build_governed_runtime_dry_run_report(gateway_report=gateway)
        second = build_governed_runtime_dry_run_report(gateway_report=gateway)

        self.assertEqual(first, second)
        self.assertEqual(gateway, before)


if __name__ == "__main__":
    unittest.main()
