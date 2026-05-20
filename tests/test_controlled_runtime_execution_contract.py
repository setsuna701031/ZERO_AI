from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ControlledRuntimeExecutionContractTest(unittest.TestCase):
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

    def _records(self, *, broken: bool = True) -> list[dict]:
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
                "parent_session_id": "missing-parent" if broken else "root",
                "repair_chain_id": "repair-1" if broken else "",
                "execution_chain_depth": 1,
                "previous_runtime_state_ref": "state-child",
            },
        }
        return [root, child]

    def _forensic_report(self, *, broken: bool = True) -> dict:
        from core.runtime.runtime_forensic_stack import build_runtime_forensic_report

        return build_runtime_forensic_report(self._records(broken=broken))

    def _landing_report(self, *, missing_rollback: bool = False, incompatible: bool = False) -> dict:
        from core.runtime.execution_landing_consistency import build_execution_landing_consistency_report

        landing = copy.deepcopy(self._flow()["landing"])
        if missing_rollback:
            del landing["rollback_result"]
        contracts = {"self_edit": landing}
        if incompatible:
            contracts["repair"] = {**self._flow()["landing"], "status": {"state": "finished"}}
        return build_execution_landing_consistency_report(contracts)

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

    def _approval_gate(self) -> dict:
        dry_run = self._dry_run()
        from core.runtime.governed_runtime_approval_gate import (
            build_governed_runtime_approval_gate_report,
        )

        return build_governed_runtime_approval_gate_report(dry_run_report=dry_run)

    def _dry_run(self) -> dict:
        from core.runtime.governance_transition_readiness import (
            build_governance_transition_readiness_report,
        )
        from core.runtime.governed_runtime_action_gateway import (
            build_governed_action_request_gateway_report,
        )
        from core.runtime.governed_runtime_dry_run_executor import (
            build_governed_runtime_dry_run_report,
        )

        forensic = self._forensic_report()
        readiness = build_governance_transition_readiness_report(
            forensic_report=forensic,
            self_edit_flow=self._flow(),
            windows_runtime_report=self._windows_ready(),
        )
        gateway = build_governed_action_request_gateway_report(
            readiness_report=readiness,
            forensic_report=forensic,
        )
        return build_governed_runtime_dry_run_report(gateway_report=gateway)

    def test_required_fields_are_stable(self) -> None:
        from core.runtime.controlled_runtime_execution_contract import (
            controlled_runtime_execution_contract_required_fields,
        )

        self.assertEqual(
            controlled_runtime_execution_contract_required_fields(),
            [
                "execution_contract_id",
                "source_approval_gate_id",
                "execution_contract_state",
                "execution_eligible",
                "approval_valid",
                "dry_run_valid",
                "evidence_ready",
                "seal_ready",
                "rollback_ready",
                "landing_ready",
                "blocking_issues",
                "affected_repair_chain_ids",
                "reason_codes",
            ],
        )

    def test_contract_ready_with_approved_gate_completed_dry_run_and_landing(self) -> None:
        from core.runtime.controlled_runtime_execution_contract import (
            build_controlled_runtime_execution_contract_report,
            validate_controlled_runtime_execution_contract_report,
        )

        gate = self._approval_gate()
        dry_run = self._dry_run()

        report = build_controlled_runtime_execution_contract_report(
            approval_gate_report=gate,
            dry_run_report=dry_run,
            landing_consistency_report=self._landing_report(),
        )
        validation = validate_controlled_runtime_execution_contract_report(report)

        self.assertTrue(report["execution_contract_id"].startswith("controlled-runtime-execution-contract-"))
        self.assertEqual(report["source_approval_gate_id"], gate["approval_gate_id"])
        self.assertEqual(report["execution_contract_state"], "contract_ready")
        self.assertTrue(report["execution_eligible"])
        self.assertTrue(report["approval_valid"])
        self.assertTrue(report["dry_run_valid"])
        self.assertTrue(report["evidence_ready"])
        self.assertTrue(report["seal_ready"])
        self.assertTrue(report["rollback_ready"])
        self.assertTrue(report["landing_ready"])
        self.assertEqual(report["affected_repair_chain_ids"], ["repair-1"])
        self.assertTrue(validation["ok"])

    def test_validates_approval_and_dry_run_helpers(self) -> None:
        from core.runtime.controlled_runtime_execution_contract import (
            validate_approval_gate_state,
            validate_dry_run_completion,
        )

        gate = self._approval_gate()
        dry_run = {
            "dry_run_id": gate["source_dry_run_id"],
            "source_gateway_id": "gateway-1",
            "dry_run_state": "dry_run_completed",
            "simulated_actions": [{"request_id": "request-1"}],
            "rejected_actions": [],
            "approval_required_actions": [],
            "evidence_refs": gate["evidence_refs"],
            "seal_refs": gate["seal_refs"],
            "affected_repair_chain_ids": gate["affected_repair_chain_ids"],
            "blocking_issues": [],
            "reason_codes": [],
        }

        self.assertTrue(validate_approval_gate_state(gate)["ok"])
        self.assertTrue(validate_dry_run_completion(dry_run)["ok"])

    def test_blocks_when_approval_gate_not_approved(self) -> None:
        from core.runtime.controlled_runtime_execution_contract import (
            build_controlled_runtime_execution_contract_report,
        )

        gate = self._approval_gate()
        dry_run = self._dry_run()
        gate["approval_state"] = "needs_review"
        gate["execution_eligible"] = False

        report = build_controlled_runtime_execution_contract_report(
            approval_gate_report=gate,
            dry_run_report=dry_run,
            landing_consistency_report=self._landing_report(),
        )

        self.assertEqual(report["execution_contract_state"], "needs_review")
        self.assertFalse(report["approval_valid"])
        self.assertIn("approval_not_approved", report["reason_codes"])

    def test_blocks_when_dry_run_not_completed(self) -> None:
        from core.runtime.controlled_runtime_execution_contract import (
            build_controlled_runtime_execution_contract_report,
        )

        gate = self._approval_gate()
        dry_run = {
            "dry_run_id": gate["source_dry_run_id"],
            "source_gateway_id": "gateway-1",
            "dry_run_state": "needs_review",
            "simulated_actions": [],
            "rejected_actions": [],
            "approval_required_actions": [{"request_id": "request-1"}],
            "evidence_refs": gate["evidence_refs"],
            "seal_refs": gate["seal_refs"],
            "affected_repair_chain_ids": gate["affected_repair_chain_ids"],
            "blocking_issues": [],
            "reason_codes": [],
        }

        report = build_controlled_runtime_execution_contract_report(
            approval_gate_report=gate,
            dry_run_report=dry_run,
            landing_consistency_report=self._landing_report(),
        )

        self.assertEqual(report["execution_contract_state"], "blocked")
        self.assertFalse(report["dry_run_valid"])
        self.assertIn("dry_run_not_completed", report["reason_codes"])

    def test_blocks_missing_evidence_and_seal_refs(self) -> None:
        from core.runtime.controlled_runtime_execution_contract import (
            build_controlled_runtime_execution_contract_report,
            validate_execution_evidence_and_seal_refs,
        )

        gate = self._approval_gate()
        dry_run = self._dry_run()
        gate["evidence_refs"] = {}
        gate["seal_refs"] = {}
        dry_run["evidence_refs"] = {}
        dry_run["seal_refs"] = {}

        validation = validate_execution_evidence_and_seal_refs(evidence_refs={}, seal_refs={})
        report = build_controlled_runtime_execution_contract_report(
            approval_gate_report=gate,
            dry_run_report=dry_run,
            landing_consistency_report=self._landing_report(),
        )

        self.assertFalse(validation["ok"])
        self.assertEqual(report["execution_contract_state"], "blocked")
        self.assertIn("missing_evidence_refs", report["reason_codes"])
        self.assertIn("missing_seal_refs", report["reason_codes"])

    def test_blocks_missing_rollback_or_incompatible_landing(self) -> None:
        from core.runtime.controlled_runtime_execution_contract import (
            build_controlled_runtime_execution_contract_report,
            validate_execution_landing_contract_compatibility,
            validate_rollback_evidence_readiness,
        )

        gate = self._approval_gate()
        dry_run = self._dry_run()
        missing_rollback = self._landing_report(missing_rollback=True)
        incompatible = self._landing_report(incompatible=True)

        rollback_validation = validate_rollback_evidence_readiness(missing_rollback)
        landing_validation = validate_execution_landing_contract_compatibility(incompatible)
        rollback_report = build_controlled_runtime_execution_contract_report(
            approval_gate_report=gate,
            dry_run_report=dry_run,
            landing_consistency_report=missing_rollback,
        )
        landing_report = build_controlled_runtime_execution_contract_report(
            approval_gate_report=gate,
            dry_run_report=dry_run,
            landing_consistency_report=incompatible,
        )

        self.assertFalse(rollback_validation["rollback_ready"])
        self.assertFalse(landing_validation["landing_ready"])
        self.assertEqual(rollback_report["execution_contract_state"], "blocked")
        self.assertEqual(landing_report["execution_contract_state"], "blocked")

    def test_execution_eligibility_summary_is_data_only(self) -> None:
        from core.runtime.controlled_runtime_execution_contract import (
            build_controlled_runtime_execution_contract_report,
            build_execution_eligibility_summary,
        )

        report = build_controlled_runtime_execution_contract_report(
            approval_gate_report=self._approval_gate(),
            dry_run_report=self._dry_run(),
            landing_consistency_report=self._landing_report(),
        )
        summary = build_execution_eligibility_summary(report)

        self.assertTrue(summary["execution_eligible"])
        self.assertFalse(summary["execute"])
        self.assertFalse(summary["planner_invoked"])
        self.assertFalse(summary["task_enqueued"])

    def test_validate_contract_report_shape(self) -> None:
        from core.runtime.controlled_runtime_execution_contract import (
            validate_controlled_runtime_execution_contract_report,
        )

        invalid = validate_controlled_runtime_execution_contract_report(
            {
                "execution_contract_id": "contract-1",
                "source_approval_gate_id": "gate-1",
                "execution_contract_state": "almost",
                "execution_eligible": False,
                "approval_valid": False,
                "dry_run_valid": False,
                "evidence_ready": False,
                "seal_ready": False,
                "rollback_ready": False,
                "landing_ready": False,
                "blocking_issues": {},
                "affected_repair_chain_ids": [],
                "reason_codes": [],
            }
        )
        missing = validate_controlled_runtime_execution_contract_report({})

        self.assertFalse(invalid["ok"])
        self.assertEqual(
            [item["field"] for item in invalid["invalid_fields"]],
            ["execution_contract_state", "blocking_issues"],
        )
        self.assertFalse(missing["ok"])
        self.assertIn("execution_contract_id", missing["missing_fields"])

    def test_builder_is_stable_and_does_not_mutate_inputs(self) -> None:
        from core.runtime.controlled_runtime_execution_contract import (
            build_controlled_runtime_execution_contract_report,
        )

        gate = self._approval_gate()
        dry_run = self._dry_run()
        landing = self._landing_report()
        gate_before = copy.deepcopy(gate)
        dry_run_before = copy.deepcopy(dry_run)
        landing_before = copy.deepcopy(landing)

        first = build_controlled_runtime_execution_contract_report(
            approval_gate_report=gate,
            dry_run_report=dry_run,
            landing_consistency_report=landing,
        )
        second = build_controlled_runtime_execution_contract_report(
            approval_gate_report=gate,
            dry_run_report=dry_run,
            landing_consistency_report=landing,
        )

        self.assertEqual(first, second)
        self.assertEqual(gate, gate_before)
        self.assertEqual(dry_run, dry_run_before)
        self.assertEqual(landing, landing_before)


if __name__ == "__main__":
    unittest.main()
