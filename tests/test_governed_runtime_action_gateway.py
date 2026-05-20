from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class GovernedRuntimeActionGatewayTest(unittest.TestCase):
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

    def _readiness(self, *, broken: bool = False) -> dict:
        from core.runtime.governance_transition_readiness import (
            build_governance_transition_readiness_report,
        )

        return build_governance_transition_readiness_report(
            forensic_report=self._forensic_report(broken=broken),
            self_edit_flow=self._flow(),
            windows_runtime_report=self._windows_ready(),
        )

    def test_gateway_constants_are_stable(self) -> None:
        from core.runtime.governed_runtime_action_gateway import (
            governed_action_request_types,
            governed_runtime_action_gateway_required_fields,
        )

        self.assertEqual(
            governed_action_request_types(),
            [
                "no_action",
                "dry_run_repair",
                "dry_run_replay",
                "dry_run_planner_handoff",
                "approval_required_repair",
                "approval_required_replay",
                "blocked",
            ],
        )
        self.assertEqual(
            governed_runtime_action_gateway_required_fields(),
            [
                "gateway_id",
                "input_readiness_id",
                "gateway_state",
                "action_requests",
                "approval_required",
                "dry_run_only",
                "blocking_issues",
                "evidence_refs",
                "seal_refs",
                "affected_repair_chain_ids",
                "reason_codes",
            ],
        )

    def test_ready_readiness_produces_no_action_gateway_report(self) -> None:
        from core.runtime.governed_runtime_action_gateway import (
            build_governed_action_request_gateway_report,
            validate_governed_action_gateway_report,
        )

        forensic = self._forensic_report()
        readiness = self._readiness()

        report = build_governed_action_request_gateway_report(
            readiness_report=readiness,
            forensic_report=forensic,
        )
        validation = validate_governed_action_gateway_report(report)

        self.assertTrue(report["gateway_id"].startswith("governed-runtime-action-gateway-"))
        self.assertEqual(report["input_readiness_id"], readiness["readiness_id"])
        self.assertEqual(report["gateway_state"], "ready")
        self.assertTrue(report["dry_run_only"])
        self.assertFalse(report["approval_required"])
        self.assertEqual(report["action_requests"][0]["request_type"], "no_action")
        self.assertFalse(report["action_requests"][0]["execute"])
        self.assertFalse(report["action_requests"][0]["planner_invoked"])
        self.assertFalse(report["action_requests"][0]["task_enqueued"])
        self.assertEqual(report["evidence_refs"]["forensic_report_id"], forensic["report_id"])
        self.assertTrue(report["seal_refs"]["snapshot_seal_id"])
        self.assertTrue(validation["ok"])

    def test_needs_review_readiness_produces_dry_run_repair_request(self) -> None:
        from core.runtime.governed_runtime_action_gateway import (
            build_dry_run_action_plan,
            build_governed_action_request_gateway_report,
        )

        forensic = self._forensic_report(broken=True)
        readiness = self._readiness(broken=True)

        report = build_governed_action_request_gateway_report(
            readiness_report=readiness,
            forensic_report=forensic,
        )
        plan = build_dry_run_action_plan(readiness, forensic_report=forensic)

        self.assertEqual(readiness["transition_state"], "needs_review")
        self.assertEqual(report["gateway_state"], "dry_run_only")
        self.assertEqual(report["action_requests"][0]["request_type"], "dry_run_repair")
        self.assertTrue(report["action_requests"][0]["dry_run_only"])
        self.assertEqual(report["affected_repair_chain_ids"], ["repair-1"])
        self.assertIn("parent_session_id_not_found", report["reason_codes"])
        self.assertEqual(plan["plan_type"], "dry_run_only")
        self.assertEqual(plan["action_requests"][0]["request_type"], "dry_run_repair")

    def test_approval_required_requests_are_data_only(self) -> None:
        from core.runtime.governed_runtime_action_gateway import (
            build_approval_required_action_requests,
            build_governed_action_request_gateway_report,
        )

        forensic = self._forensic_report(broken=True)
        readiness = self._readiness(broken=True)

        report = build_governed_action_request_gateway_report(
            readiness_report=readiness,
            forensic_report=forensic,
            approval_required=True,
            dry_run_only=False,
        )
        requests = build_approval_required_action_requests(readiness, forensic_report=forensic)

        self.assertEqual(report["gateway_state"], "approval_required")
        self.assertTrue(report["approval_required"])
        self.assertFalse(report["dry_run_only"])
        self.assertEqual(report["action_requests"][0]["request_type"], "approval_required_repair")
        self.assertEqual(requests[0]["request_type"], "approval_required_repair")
        self.assertFalse(report["action_requests"][0]["execute"])

    def test_replay_and_planner_actions_map_to_dry_run_request_types(self) -> None:
        from core.runtime.governed_runtime_action_gateway import (
            map_recommended_actions_to_action_requests,
        )

        requests = map_recommended_actions_to_action_requests(
            [
                {"action_type": "replay_recommended", "reason_codes": ["replay_drift_detected"]},
                {"action_type": "planner_handoff_recommended", "reason_codes": ["planner_handoff"]},
            ],
            dry_run_only=True,
            reason_codes=[],
        )

        self.assertEqual(
            [item["request_type"] for item in requests],
            ["dry_run_replay", "dry_run_planner_handoff"],
        )

    def test_blocked_readiness_blocks_action_requests(self) -> None:
        from core.runtime.governance_transition_readiness import (
            build_governance_transition_readiness_report,
        )
        from core.runtime.governed_runtime_action_gateway import (
            build_governed_action_request_gateway_report,
            validate_readiness_for_action_request_creation,
        )

        windows = self._windows_ready()
        windows["blocking_issues"] = [{"kind": "base_interpreter_missing", "path": "C:\\missing\\python.exe"}]
        readiness = build_governance_transition_readiness_report(
            forensic_report=self._forensic_report(),
            self_edit_flow=self._flow(),
            windows_runtime_report=windows,
        )

        validation = validate_readiness_for_action_request_creation(readiness)
        report = build_governed_action_request_gateway_report(readiness_report=readiness)

        self.assertFalse(validation["ok"])
        self.assertEqual(report["gateway_state"], "blocked")
        self.assertEqual(report["action_requests"][0]["request_type"], "blocked")
        self.assertIn("readiness_blocked", report["reason_codes"])

    def test_builds_gateway_from_source_reports_when_readiness_missing(self) -> None:
        from core.runtime.governed_runtime_action_gateway import (
            build_governed_action_request_gateway_report,
        )

        report = build_governed_action_request_gateway_report(
            forensic_report=self._forensic_report(),
            self_edit_flow=self._flow(),
            windows_runtime_report=self._windows_ready(),
        )

        self.assertEqual(report["gateway_state"], "ready")
        self.assertTrue(report["input_readiness_id"])
        self.assertEqual(report["action_requests"][0]["request_type"], "no_action")

    def test_validate_gateway_report_shape(self) -> None:
        from core.runtime.governed_runtime_action_gateway import (
            validate_governed_action_gateway_report,
        )

        invalid = validate_governed_action_gateway_report(
            {
                "gateway_id": "gateway-1",
                "input_readiness_id": "readiness-1",
                "gateway_state": "almost",
                "action_requests": [{"request_type": "execute_now"}],
                "approval_required": False,
                "dry_run_only": True,
                "blocking_issues": [],
                "evidence_refs": {},
                "seal_refs": {},
                "affected_repair_chain_ids": [],
                "reason_codes": [],
            }
        )
        missing = validate_governed_action_gateway_report({})

        self.assertFalse(invalid["ok"])
        self.assertEqual(
            [item["field"] for item in invalid["invalid_fields"]],
            ["gateway_state", "action_requests"],
        )
        self.assertFalse(missing["ok"])
        self.assertIn("gateway_id", missing["missing_fields"])

    def test_gateway_builder_is_stable_and_does_not_mutate_inputs(self) -> None:
        from core.runtime.governed_runtime_action_gateway import (
            build_governed_action_request_gateway_report,
        )

        forensic = self._forensic_report(broken=True)
        readiness = self._readiness(broken=True)
        forensic_before = copy.deepcopy(forensic)
        readiness_before = copy.deepcopy(readiness)

        first = build_governed_action_request_gateway_report(
            readiness_report=readiness,
            forensic_report=forensic,
        )
        second = build_governed_action_request_gateway_report(
            readiness_report=readiness,
            forensic_report=forensic,
        )

        self.assertEqual(first, second)
        self.assertEqual(forensic, forensic_before)
        self.assertEqual(readiness, readiness_before)


if __name__ == "__main__":
    unittest.main()
