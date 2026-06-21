from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ControlledRuntimeExecutionBoundaryTest(unittest.TestCase):
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

    def _records(self) -> list[dict]:
        return [
            {
                "status": "finished",
                "engineering_continuity": {
                    "session_id": "root",
                    "execution_chain_depth": 0,
                    "previous_runtime_state_ref": "state-root",
                },
            },
            {
                "status": "finished",
                "engineering_continuity": {
                    "session_id": "child",
                    "parent_session_id": "missing-parent",
                    "repair_chain_id": "repair-1",
                    "execution_chain_depth": 1,
                    "previous_runtime_state_ref": "state-child",
                },
            },
        ]

    def _forensic_report(self) -> dict:
        from core.runtime.runtime_forensic_stack import build_runtime_forensic_report

        return build_runtime_forensic_report(self._records())

    def _landing_report(self, *, missing_rollback: bool = False) -> dict:
        from core.runtime.execution_landing_consistency import build_execution_landing_consistency_report

        landing = copy.deepcopy(self._flow()["landing"])
        if missing_rollback:
            del landing["rollback_result"]
        return build_execution_landing_consistency_report({"self_edit": landing})

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

    def _contract_and_requests(self) -> tuple[dict, list[dict]]:
        from core.runtime.controlled_runtime_execution_contract import (
            build_controlled_runtime_execution_contract_report,
        )
        from core.runtime.governance_transition_readiness import (
            build_governance_transition_readiness_report,
        )
        from core.runtime.governed_runtime_action_gateway import (
            build_governed_action_request_gateway_report,
        )
        from core.runtime.governed_runtime_approval_gate import (
            build_governed_runtime_approval_gate_report,
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
        dry_run = build_governed_runtime_dry_run_report(gateway_report=gateway)
        approval = build_governed_runtime_approval_gate_report(dry_run_report=dry_run)
        contract = build_controlled_runtime_execution_contract_report(
            approval_gate_report=approval,
            dry_run_report=dry_run,
            landing_consistency_report=self._landing_report(),
        )
        return contract, gateway["action_requests"]

    def _capability_grant(self, *, expired: bool = False, delegation_allowed: bool = True, delegation_chain: list[dict] | None = None) -> dict:
        grant = {
            "granted_capabilities": [
                "runtime.governed_mutation",
                "runtime.approval",
                "runtime.rollback",
                "runtime.replay",
                "runtime.scheduler_owner",
                "runtime.persistence_service_write",
                "runtime.external_side_effect",
                "runtime.audit",
            ],
            "grant_source": "test-governance",
            "grant_scope": "controlled-runtime-boundary-tests",
            "grant_expiration": "2000-01-01T00:00:00+00:00" if expired else "2999-01-01T00:00:00+00:00",
            "delegation_allowed": delegation_allowed,
        }
        if delegation_chain is not None:
            grant["delegation_chain"] = delegation_chain
        return grant

    def _approval_chain(
        self,
        *,
        expired: bool = False,
        approved_intents: list[str] | None = None,
        approved_capabilities: list[str] | None = None,
        approval_scope: str = "controlled-runtime-boundary-tests",
        forged: bool = False,
        omit_signature: bool = False,
    ) -> dict:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_runtime_approval_signature,
        )

        approval = {
            "approval_id": "approval-1",
            "approval_source": "test-review",
            "approval_scope": approval_scope,
            "approved_intents": approved_intents or [
                "governed_mutation",
                "external_side_effect",
                "persistence_write",
                "scheduler_control",
            ],
            "approved_capabilities": approved_capabilities or self._capability_grant()["granted_capabilities"],
            "approval_timestamp": "2026-01-01T00:00:00+00:00",
            "approval_expiration": "2000-01-01T00:00:00+00:00" if expired else "2999-01-01T00:00:00+00:00",
            "review_required": False,
        }
        if not omit_signature:
            approval["approval_signature"] = build_runtime_approval_signature(approval)
            if forged:
                approval["approval_signature"] = "runtime-approval-forged"
        return approval

    def test_constants_are_stable(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            controlled_runtime_allowed_action_types,
            controlled_runtime_execution_boundary_required_fields,
            controlled_runtime_forbidden_flags,
            controlled_runtime_execution_intents,
        )

        self.assertEqual(
            controlled_runtime_allowed_action_types(),
            [
                "no_action",
                "dry_run_repair",
                "dry_run_replay",
                "dry_run_planner_handoff",
                "approval_required_repair",
                "approval_required_replay",
            ],
        )
        self.assertEqual(
            controlled_runtime_forbidden_flags(),
            [
                "execute",
                "planner_invoked",
                "task_enqueued",
                "scheduler_mutated",
                "executor_mutated",
                "persistence_written",
                "ui_invoked",
            ],
        )
        self.assertEqual(
            controlled_runtime_execution_boundary_required_fields(),
            [
                "boundary_id",
                "source_execution_contract_id",
                "boundary_state",
                "allowed_action_types",
                "forbidden_flags_detected",
                "boundary_ready",
                "execution_allowed",
                "evidence_boundary_ready",
                "seal_boundary_ready",
                "rollback_boundary_ready",
                "blocking_issues",
                "reason_codes",
                "execution_intent",
                "governance_reason",
                "violated_constraints",
                "required_capabilities",
                "missing_capabilities",
                "unauthorized_capabilities",
                "delegation_chain_valid",
                "capability_grant_state",
                "approval_chain_valid",
                "approval_required",
                "approval_state",
                "approval_mismatch_reason",
                "approved_execution_scope",
                "transaction_state",
                "transition_valid",
                "rollback_state",
                "verification_state",
                "seal_state",
                "replay_consistency_state",
                "evidence_chain_valid",
                "evidence_integrity_state",
                "replay_evidence_consistent",
                "evidence_tamper_detected",
                "evidence_seal_valid",
                "reconstruction_state",
                "reconstruction_consistent",
                "replay_order_valid",
                "reconstruction_divergence_detected",
                "rollback_reconstruction_valid",
                "seal_reconstruction_valid",
                "governance_chain_sealable",
                "governance_chain_state",
                "seal_blockers",
                "seal_warnings",
            ],
        )
        self.assertEqual(
            controlled_runtime_execution_intents(),
            [
                "read_only",
                "local_mutation",
                "governed_mutation",
                "external_side_effect",
                "persistence_write",
                "scheduler_control",
                "executor_control",
            ],
        )

    def test_boundary_ready_for_contract_and_allowed_dry_run_requests(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
            validate_controlled_runtime_execution_boundary_report,
        )

        contract, requests = self._contract_and_requests()

        report = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=self._landing_report(),
            capability_grant_contract=self._capability_grant(),
            approval_chain_contract=self._approval_chain(),
        )
        validation = validate_controlled_runtime_execution_boundary_report(report)

        self.assertTrue(report["boundary_id"].startswith("controlled-runtime-execution-boundary-"))
        self.assertEqual(report["source_execution_contract_id"], contract["execution_contract_id"])
        self.assertEqual(report["boundary_state"], "boundary_ready")
        self.assertTrue(report["boundary_ready"])
        self.assertTrue(report["execution_allowed"])
        self.assertTrue(report["evidence_boundary_ready"])
        self.assertTrue(report["seal_boundary_ready"])
        self.assertTrue(report["rollback_boundary_ready"])
        self.assertEqual(report["execution_intent"], "governed_mutation")
        self.assertIn("mutation_intent_requires_governance", report["governance_reason"])
        self.assertEqual(report["violated_constraints"], [])
        self.assertIn("runtime.governed_mutation", report["required_capabilities"])
        self.assertEqual(report["missing_capabilities"], [])
        self.assertEqual(report["unauthorized_capabilities"], [])
        self.assertTrue(report["delegation_chain_valid"])
        self.assertEqual(report["capability_grant_state"], "grant_valid")
        self.assertTrue(report["approval_chain_valid"])
        self.assertTrue(report["approval_required"])
        self.assertEqual(report["approval_state"], "approval_valid")
        self.assertEqual(report["approval_mismatch_reason"], [])
        self.assertEqual(report["approved_execution_scope"], "controlled-runtime-boundary-tests")
        self.assertEqual(report["forbidden_flags_detected"], [])
        self.assertTrue(report["governance_chain_sealable"])
        self.assertEqual(report["governance_chain_state"], "warning")
        self.assertEqual(report["seal_blockers"], [])
        self.assertIn("runtime_governance_chain_seal", report)
        self.assertTrue(validation["ok"])

    def test_execution_intent_classification_correctness(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            classify_runtime_execution_intent,
        )

        cases = [
            ({"request_type": "no_action"}, "read_only"),
            ({"request_type": "no_action", "action": "write_file"}, "local_mutation"),
            ({"request_type": "dry_run_repair"}, "governed_mutation"),
            ({"request_type": "no_action", "network": True}, "external_side_effect"),
            ({"request_type": "no_action", "persistence_written": True}, "persistence_write"),
            ({"request_type": "no_action", "scheduler_mutated": True}, "scheduler_control"),
            ({"request_type": "no_action", "execute": True}, "executor_control"),
        ]

        for request, expected in cases:
            with self.subTest(expected=expected):
                result = classify_runtime_execution_intent([request])
                self.assertEqual(result["execution_intent"], expected)

    def test_hidden_mutation_escalation_detection(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
            classify_runtime_execution_intent,
        )

        request = {
            "request_id": "hidden-1",
            "request_type": "no_action",
            "execution_intent": "read_only",
            "action": "write_file",
        }
        classification = classify_runtime_execution_intent([request])
        self.assertEqual(classification["execution_intent"], "local_mutation")
        self.assertIn("hidden_mutation_escalation", classification["reason_codes"])

        contract, _requests = self._contract_and_requests()
        report = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=[request],
            landing_consistency_report=self._landing_report(),
            capability_grant_contract=self._capability_grant(),
            approval_chain_contract=self._approval_chain(),
        )

        self.assertEqual(report["boundary_state"], "blocked")
        self.assertIn("hidden_mutation_escalation", report["reason_codes"])
        self.assertIn("hidden_mutation_escalation", report["violated_constraints"])

    def test_governance_reason_and_capability_requirement_generation(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_execution_intent_governance,
        )

        governance = build_execution_intent_governance(
            execution_intent="scheduler_control",
            action_requests=[{"request_type": "no_action", "scheduler_mutated": True}],
            blocking_issues=[],
            forbidden_flags=[
                {
                    "kind": "forbidden_flag_detected",
                    "flag": "scheduler_mutated",
                    "index": 0,
                    "request_id": "",
                }
            ],
        )

        self.assertIn("scheduler_control_requires_scheduler_owner", governance["governance_reason"])
        self.assertIn("scheduler_control_boundary", governance["violated_constraints"])
        self.assertIn("runtime.scheduler_owner", governance["required_capabilities"])

    def test_granted_capability_passes(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
        )

        contract, requests = self._contract_and_requests()
        report = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=self._landing_report(),
            capability_grant_contract=self._capability_grant(),
            approval_chain_contract=self._approval_chain(),
        )

        self.assertEqual(report["boundary_state"], "boundary_ready")
        self.assertEqual(report["capability_grant_state"], "grant_valid")
        self.assertEqual(report["missing_capabilities"], [])

    def test_missing_capability_blocks(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
        )

        contract, requests = self._contract_and_requests()
        grant = self._capability_grant()
        grant["granted_capabilities"] = ["runtime.approval"]

        report = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=self._landing_report(),
            capability_grant_contract=grant,
            approval_chain_contract=self._approval_chain(),
        )

        self.assertEqual(report["boundary_state"], "blocked")
        self.assertEqual(report["capability_grant_state"], "unauthorized")
        self.assertIn("runtime.governed_mutation", report["missing_capabilities"])

    def test_expired_grant_blocks(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
        )

        contract, requests = self._contract_and_requests()
        report = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=self._landing_report(),
            capability_grant_contract=self._capability_grant(expired=True),
            approval_chain_contract=self._approval_chain(),
        )

        self.assertEqual(report["boundary_state"], "blocked")
        self.assertEqual(report["capability_grant_state"], "grant_expired")
        self.assertIn("capability_grant_expired", report["reason_codes"])

    def test_invalid_delegation_blocks(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
        )

        contract, requests = self._contract_and_requests()
        report = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=self._landing_report(),
            capability_grant_contract=self._capability_grant(
                delegation_allowed=False,
                delegation_chain=[{"delegator": "root", "delegate": "child"}],
            ),
            approval_chain_contract=self._approval_chain(),
        )

        self.assertEqual(report["boundary_state"], "blocked")
        self.assertEqual(report["capability_grant_state"], "invalid_delegation")
        self.assertFalse(report["delegation_chain_valid"])

    def test_valid_approval_passes(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
        )

        contract, requests = self._contract_and_requests()
        report = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=self._landing_report(),
            capability_grant_contract=self._capability_grant(),
            approval_chain_contract=self._approval_chain(),
        )

        self.assertEqual(report["boundary_state"], "boundary_ready")
        self.assertTrue(report["approval_chain_valid"])
        self.assertTrue(report["approval_required"])
        self.assertEqual(report["approval_state"], "approval_valid")

    def test_missing_approval_blocks(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
        )

        contract, requests = self._contract_and_requests()
        report = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=self._landing_report(),
            capability_grant_contract=self._capability_grant(),
        )

        self.assertEqual(report["boundary_state"], "blocked")
        self.assertEqual(report["approval_state"], "approval_missing")
        self.assertFalse(report["approval_chain_valid"])

    def test_expired_approval_blocks(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
        )

        contract, requests = self._contract_and_requests()
        report = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=self._landing_report(),
            capability_grant_contract=self._capability_grant(),
            approval_chain_contract=self._approval_chain(expired=True),
        )

        self.assertEqual(report["boundary_state"], "blocked")
        self.assertEqual(report["approval_state"], "approval_expired")
        self.assertIn("approval_expired", report["reason_codes"])

    def test_mismatched_approval_blocks(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
        )

        contract, requests = self._contract_and_requests()
        report = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=self._landing_report(),
            capability_grant_contract=self._capability_grant(),
            approval_chain_contract=self._approval_chain(
                approved_intents=["external_side_effect"],
            ),
        )

        self.assertEqual(report["boundary_state"], "blocked")
        self.assertEqual(report["approval_state"], "approval_mismatch")
        self.assertIn("intent_not_approved", report["approval_mismatch_reason"])

    def test_forged_approval_metadata_blocks(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
        )

        contract, requests = self._contract_and_requests()
        report = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=self._landing_report(),
            capability_grant_contract=self._capability_grant(),
            approval_chain_contract=self._approval_chain(forged=True),
        )

        self.assertEqual(report["boundary_state"], "blocked")
        self.assertEqual(report["approval_state"], "approval_forged")
        self.assertIn("approval_signature_invalid", report["reason_codes"])

    def test_capability_and_approval_interaction_blocks_unapproved_capability(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
        )

        contract, requests = self._contract_and_requests()
        approved = [
            capability
            for capability in self._capability_grant()["granted_capabilities"]
            if capability != "runtime.governed_mutation"
        ]
        report = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=self._landing_report(),
            capability_grant_contract=self._capability_grant(),
            approval_chain_contract=self._approval_chain(approved_capabilities=approved),
        )

        self.assertEqual(report["boundary_state"], "blocked")
        self.assertEqual(report["capability_grant_state"], "grant_valid")
        self.assertEqual(report["approval_state"], "approval_mismatch")
        self.assertIn("capability_not_approved", report["approval_mismatch_reason"])

    def test_executor_scheduler_and_persistence_escalations_block(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
        )

        cases = [
            ("executor_control", {"request_type": "no_action", "execute": True}, "executor_ownership_boundary"),
            ("scheduler_control", {"request_type": "no_action", "scheduler_mutated": True}, "scheduler_control_boundary"),
            ("persistence_write", {"request_type": "no_action", "persistence_written": True}, "persistence_ownership_boundary"),
        ]
        contract, _requests = self._contract_and_requests()

        for expected_intent, request, constraint in cases:
            with self.subTest(expected_intent=expected_intent):
                report = build_controlled_runtime_execution_boundary_report(
                    execution_contract_report=contract,
                    action_requests=[request],
                    landing_consistency_report=self._landing_report(),
                    capability_grant_contract=self._capability_grant(),
                    approval_chain_contract=self._approval_chain(),
                )
                self.assertEqual(report["boundary_state"], "blocked")
                self.assertEqual(report["execution_intent"], expected_intent)
                self.assertIn(constraint, report["violated_constraints"])

    def test_detects_forbidden_execution_side_effects_and_runtime_coupling(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            detect_forbidden_execution_side_effects,
            detect_forbidden_runtime_coupling,
        )

        request = {
            "request_id": "request-1",
            "request_type": "dry_run_repair",
            "execute": True,
            "planner_invoked": True,
            "scheduler_mutated": True,
        }

        side_effects = detect_forbidden_execution_side_effects([request])
        coupling = detect_forbidden_runtime_coupling([request])

        self.assertEqual(
            sorted(item["flag"] for item in side_effects),
            ["execute", "planner_invoked", "scheduler_mutated"],
        )
        self.assertEqual(
            sorted(item["flag"] for item in coupling),
            ["planner_invoked", "scheduler_mutated"],
        )

    def test_blocks_forbidden_flags(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
        )

        contract, requests = self._contract_and_requests()
        requests[0]["execute"] = True

        report = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=self._landing_report(),
            capability_grant_contract=self._capability_grant(),
            approval_chain_contract=self._approval_chain(),
        )

        self.assertEqual(report["boundary_state"], "blocked")
        self.assertFalse(report["execution_allowed"])
        self.assertIn("forbidden_flag_detected", report["reason_codes"])

    def test_blocks_disallowed_action_types(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
            validate_allowed_action_request_types,
        )

        contract, requests = self._contract_and_requests()
        requests[0]["request_type"] = "blocked"

        validation = validate_allowed_action_request_types(requests)
        report = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=self._landing_report(),
            capability_grant_contract=self._capability_grant(),
            approval_chain_contract=self._approval_chain(),
        )

        self.assertFalse(validation["ok"])
        self.assertEqual(report["boundary_state"], "blocked")
        self.assertIn("action_type_not_allowed", report["reason_codes"])

    def test_blocks_missing_evidence_seal_or_rollback_boundary(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
            validate_boundary_evidence_seal_rollback_readiness,
        )

        contract, requests = self._contract_and_requests()
        contract["evidence_refs"] = {}
        contract["seal_refs"] = {}
        contract["rollback_ready"] = False

        boundary_validation = validate_boundary_evidence_seal_rollback_readiness(contract)
        report = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=self._landing_report(missing_rollback=True),
            capability_grant_contract=self._capability_grant(),
            approval_chain_contract=self._approval_chain(),
        )

        self.assertFalse(boundary_validation["ok"])
        self.assertEqual(report["boundary_state"], "blocked")
        self.assertIn("evidence_boundary_not_ready", report["reason_codes"])
        self.assertIn("seal_boundary_not_ready", report["reason_codes"])
        self.assertIn("rollback_boundary_not_ready", report["reason_codes"])

    def test_needs_review_when_contract_not_eligible_but_not_blocked(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
        )

        contract, requests = self._contract_and_requests()
        contract["execution_contract_state"] = "needs_review"
        contract["execution_eligible"] = False

        report = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=self._landing_report(),
            capability_grant_contract=self._capability_grant(),
            approval_chain_contract=self._approval_chain(),
        )

        self.assertEqual(report["boundary_state"], "needs_review")
        self.assertFalse(report["execution_allowed"])

    def test_boundary_summary_is_data_only(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_execution_boundary_summary,
            build_controlled_runtime_execution_boundary_report,
        )

        contract, requests = self._contract_and_requests()
        report = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=self._landing_report(),
            capability_grant_contract=self._capability_grant(),
            approval_chain_contract=self._approval_chain(),
        )
        summary = build_controlled_execution_boundary_summary(report)

        self.assertTrue(summary["boundary_ready"])
        self.assertFalse(summary["execute"])
        self.assertFalse(summary["planner_invoked"])
        self.assertFalse(summary["task_enqueued"])

    def test_validate_boundary_report_shape(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            validate_controlled_runtime_execution_boundary_report,
        )

        invalid = validate_controlled_runtime_execution_boundary_report(
            {
                "boundary_id": "boundary-1",
                "source_execution_contract_id": "contract-1",
                "boundary_state": "almost",
                "allowed_action_types": {},
                "forbidden_flags_detected": [],
                "boundary_ready": False,
                "execution_allowed": False,
                "evidence_boundary_ready": False,
                "seal_boundary_ready": False,
                "rollback_boundary_ready": False,
                "blocking_issues": [],
                "reason_codes": [],
                "execution_intent": "almost",
                "governance_reason": {},
                "violated_constraints": [],
                "required_capabilities": [],
                "missing_capabilities": [],
                "unauthorized_capabilities": [],
                "delegation_chain_valid": "yes",
                "capability_grant_state": "almost",
                "approval_chain_valid": "yes",
                "approval_required": "yes",
                "approval_state": "almost",
                "approval_mismatch_reason": {},
                "approved_execution_scope": "scope",
                "transaction_state": "executing",
                "transition_valid": "yes",
                "rollback_state": "ready",
                "verification_state": "verified",
                "seal_state": "sealed",
                "replay_consistency_state": "consistent",
                "evidence_chain_valid": "yes",
                "evidence_integrity_state": "valid",
                "replay_evidence_consistent": "yes",
                "evidence_tamper_detected": "no",
                "evidence_seal_valid": "yes",
                "reconstruction_state": "consistent",
                "reconstruction_consistent": "yes",
                "replay_order_valid": "yes",
                "reconstruction_divergence_detected": "no",
                "rollback_reconstruction_valid": "yes",
                "seal_reconstruction_valid": "yes",
            }
        )
        missing = validate_controlled_runtime_execution_boundary_report({})

        self.assertFalse(invalid["ok"])
        self.assertEqual(
            [item["field"] for item in invalid["invalid_fields"]],
            [
                "boundary_state",
                "execution_intent",
                "allowed_action_types",
                "governance_reason",
                "approval_mismatch_reason",
                "delegation_chain_valid",
                "capability_grant_state",
                "approval_chain_valid",
                "approval_required",
                "approval_state",
                "transition_valid",
                "evidence_chain_valid",
                "replay_evidence_consistent",
                "evidence_tamper_detected",
                "evidence_seal_valid",
                "reconstruction_consistent",
                "replay_order_valid",
                "reconstruction_divergence_detected",
                "rollback_reconstruction_valid",
                "seal_reconstruction_valid",
            ],
        )
        self.assertFalse(missing["ok"])
        self.assertIn("boundary_id", missing["missing_fields"])

    def test_boundary_builder_is_stable_and_does_not_mutate_inputs(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
        )

        contract, requests = self._contract_and_requests()
        contract_before = copy.deepcopy(contract)
        requests_before = copy.deepcopy(requests)

        first = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=self._landing_report(),
            capability_grant_contract=self._capability_grant(),
            approval_chain_contract=self._approval_chain(),
        )
        second = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=self._landing_report(),
            capability_grant_contract=self._capability_grant(),
            approval_chain_contract=self._approval_chain(),
        )

        self.assertEqual(first, second)
        self.assertEqual(contract, contract_before)
        self.assertEqual(requests, requests_before)

    def test_blocked_boundary_prevents_runtime_execution(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
        )
        from core.runtime.executor import Executor

        contract, requests = self._contract_and_requests()
        requests[0]["execute"] = True
        boundary = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=self._landing_report(),
            capability_grant_contract=self._capability_grant(),
            approval_chain_contract=self._approval_chain(),
        )

        with tempfile.TemporaryDirectory() as root:
            marker = Path(root) / "blocked_marker.txt"
            request = self._runtime_request(
                root=root,
                boundary=boundary,
                code=f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')",
            )

            result = Executor(workspace_root=root).execute_request(request)

            self.assertEqual(result.status, "blocked")
            self.assertTrue(result.blocked)
            self.assertFalse(marker.exists())
            self.assertEqual(
                result.metadata["controlled_runtime_execution_boundary_state"],
                "blocked",
            )

    def test_needs_review_boundary_prevents_runtime_execution_and_returns_review_state(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
        )
        from core.runtime.executor import Executor

        contract, requests = self._contract_and_requests()
        contract["execution_contract_state"] = "needs_review"
        contract["execution_eligible"] = False
        boundary = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=self._landing_report(),
            capability_grant_contract=self._capability_grant(),
            approval_chain_contract=self._approval_chain(),
        )

        with tempfile.TemporaryDirectory() as root:
            marker = Path(root) / "review_marker.txt"
            request = self._runtime_request(
                root=root,
                boundary=boundary,
                code=f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')",
            )

            result = Executor(workspace_root=root).execute_request(request)

            self.assertEqual(result.status, "review_required")
            self.assertTrue(result.blocked)
            self.assertFalse(marker.exists())
            self.assertEqual(
                result.metadata["controlled_runtime_execution_boundary_state"],
                "needs_review",
            )

    def test_boundary_ready_preserves_successful_runtime_execution(self) -> None:
        from core.runtime.controlled_runtime_execution_boundary import (
            build_controlled_runtime_execution_boundary_report,
        )
        from core.runtime.executor import Executor

        contract, requests = self._contract_and_requests()
        boundary = build_controlled_runtime_execution_boundary_report(
            execution_contract_report=contract,
            action_requests=requests,
            landing_consistency_report=self._landing_report(),
            capability_grant_contract=self._capability_grant(),
            approval_chain_contract=self._approval_chain(),
        )

        with tempfile.TemporaryDirectory() as root:
            request = self._runtime_request(
                root=root,
                boundary=boundary,
                code="print('boundary-ready')",
            )

            result = Executor(workspace_root=root).execute_request(request)

            self.assertEqual(result.status, "succeeded")
            self.assertFalse(result.blocked)
            self.assertEqual(result.stdout.strip(), "boundary-ready")
            self.assertEqual(
                result.metadata["controlled_runtime_execution_boundary_state"],
                "boundary_ready",
            )

    def _runtime_request(self, *, root: str, boundary: dict, code: str):
        from core.runtime.runtime_execution_request import RuntimeExecutionRequest

        return RuntimeExecutionRequest(
            execution_type="subprocess",
            command=(sys.executable, "-c", code),
            working_directory=root,
            timeout=20,
            metadata={
                "operation": "subprocess",
                "task_id": "controlled-boundary-runtime-request",
                "step_id": "controlled-boundary-runtime-request:execute",
                "authority_source": "runtime_dispatcher",
                "runtime_session": "runtime-session:controlled-boundary",
                "approval_state": "approved",
                "policy_result": {"allowed": True, "source": "controlled_boundary_test"},
                "trace_id": "trace:controlled-boundary-runtime-request",
                "runtime_identity": {
                    "identity_id": "system:test_controlled_runtime_execution_boundary",
                    "identity_type": "TEST",
                    "source": "tests",
                },
                "authority_scope_id": "authority:test",
                "capability_scope_id": "capability:test",
                "provenance": {
                    "source": "tests.test_controlled_runtime_execution_boundary",
                },
                "controlled_runtime_execution_boundary_report": boundary,
            },
            lineage={
                "request_id": "controlled-boundary-runtime-request",
                "execution_start_id": "execution_start:controlled-boundary-runtime-request",
            },
            replay_id="replay:controlled-boundary-runtime-request",
        )


if __name__ == "__main__":
    unittest.main()
