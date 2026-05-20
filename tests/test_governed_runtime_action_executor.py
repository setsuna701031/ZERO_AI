from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class GovernedRuntimeActionExecutorTest(unittest.TestCase):
    def _gateway(self, *, state: str = "ready", request_type: str = "no_action", dry_run_only: bool = True, approval_required: bool = False) -> dict:
        return {
            "schema_version": "governed_runtime_action_gateway.v1",
            "gateway_id": "gateway-1",
            "input_readiness_id": "readiness-1",
            "gateway_state": state,
            "action_requests": [
                {
                    "request_id": "request-1",
                    "request_type": request_type,
                    "dry_run_only": dry_run_only,
                    "approval_required": approval_required,
                    "execute": False,
                    "planner_invoked": False,
                    "task_enqueued": False,
                    "reason_codes": [],
                }
            ],
            "approval_required": approval_required,
            "dry_run_only": dry_run_only,
            "blocking_issues": [],
            "evidence_refs": {},
            "seal_refs": {},
            "affected_repair_chain_ids": [],
            "reason_codes": [],
        }

    def _boundary(self, *, state: str = "boundary_ready", execution_allowed: bool = True) -> dict:
        return {
            "boundary_id": "boundary-1",
            "boundary_state": state,
            "execution_allowed": execution_allowed,
            "reason_codes": [],
        }

    def test_constants_are_stable(self) -> None:
        from core.runtime.governed_runtime_action_executor import (
            governed_runtime_action_executor_action_types,
            governed_runtime_action_executor_required_fields,
            governed_runtime_action_executor_states,
        )

        self.assertEqual(
            governed_runtime_action_executor_states(),
            [
                "ready",
                "dry_run",
                "review_required",
                "blocked",
                "completed",
                "failed",
            ],
        )
        self.assertEqual(
            governed_runtime_action_executor_action_types(),
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
            governed_runtime_action_executor_required_fields(),
            [
                "governed_action_execution_id",
                "source_gateway_id",
                "execution_state",
                "execution_allowed",
                "dry_run_only",
                "approval_required",
                "action_results",
                "blocked_actions",
                "review_required_actions",
                "execution_summary",
                "blocking_issues",
                "reason_codes",
            ],
        )

    def test_ready_no_action_builds_completed_data_only_report(self) -> None:
        from core.runtime.governed_runtime_action_executor import (
            build_governed_runtime_action_execution_report,
            validate_governed_runtime_action_execution_report,
        )

        report = build_governed_runtime_action_execution_report(
            gateway_report=self._gateway(dry_run_only=False),
            boundary_report=self._boundary(),
        )
        validation = validate_governed_runtime_action_execution_report(report)

        self.assertTrue(report["governed_action_execution_id"].startswith("governed-runtime-action-execution-"))
        self.assertEqual(report["source_gateway_id"], "gateway-1")
        self.assertEqual(report["source_boundary_id"], "boundary-1")
        self.assertEqual(report["execution_state"], "completed")
        self.assertTrue(report["execution_allowed"])
        self.assertEqual(report["action_results"][0]["action_state"], "completed")
        self.assertFalse(report["action_results"][0]["execution_performed"])
        self.assertTrue(validation["ok"])

    def test_dry_run_repair_routes_to_dry_run_without_execution(self) -> None:
        from core.runtime.governed_runtime_action_executor import build_governed_runtime_action_execution_report

        report = build_governed_runtime_action_execution_report(
            gateway_report=self._gateway(state="dry_run_only", request_type="dry_run_repair", dry_run_only=True),
            boundary_report=self._boundary(),
        )

        self.assertEqual(report["execution_state"], "dry_run")
        self.assertFalse(report["execution_allowed"])
        self.assertEqual(report["action_results"][0]["action_state"], "dry_run")
        self.assertFalse(report["action_results"][0]["execution_performed"])

    def test_blocked_gateway_blocks_execution(self) -> None:
        from core.runtime.governed_runtime_action_executor import build_governed_runtime_action_execution_report

        report = build_governed_runtime_action_execution_report(
            gateway_report=self._gateway(state="blocked", request_type="blocked", dry_run_only=True),
            boundary_report=self._boundary(),
        )

        self.assertEqual(report["execution_state"], "blocked")
        self.assertFalse(report["execution_allowed"])
        self.assertGreaterEqual(len(report["blocked_actions"]), 1)
        self.assertIn("gateway_blocked", report["reason_codes"])

    def test_boundary_not_ready_blocks_mutating_action(self) -> None:
        from core.runtime.governed_runtime_action_executor import build_governed_runtime_action_execution_report

        report = build_governed_runtime_action_execution_report(
            gateway_report=self._gateway(state="dry_run_only", request_type="dry_run_repair", dry_run_only=True),
            boundary_report=self._boundary(state="blocked", execution_allowed=False),
        )

        self.assertEqual(report["execution_state"], "blocked")
        self.assertFalse(report["execution_allowed"])
        self.assertIn("boundary_not_ready", report["reason_codes"])
        self.assertIn("boundary_does_not_allow_action", report["reason_codes"])

    def test_approval_required_action_routes_to_review_required(self) -> None:
        from core.runtime.governed_runtime_action_executor import build_governed_runtime_action_execution_report

        report = build_governed_runtime_action_execution_report(
            gateway_report=self._gateway(
                state="approval_required",
                request_type="approval_required_repair",
                dry_run_only=False,
                approval_required=True,
            ),
            boundary_report=self._boundary(),
        )

        self.assertEqual(report["execution_state"], "review_required")
        self.assertFalse(report["execution_allowed"])
        self.assertEqual(report["action_results"][0]["action_state"], "review_required")
        self.assertEqual(len(report["review_required_actions"]), 1)

    def test_valid_approval_allows_ready_state_for_approval_action(self) -> None:
        from core.runtime.governed_runtime_action_executor import build_governed_runtime_action_execution_report

        report = build_governed_runtime_action_execution_report(
            gateway_report=self._gateway(
                state="approval_required",
                request_type="approval_required_repair",
                dry_run_only=False,
                approval_required=True,
            ),
            boundary_report=self._boundary(),
            approval_context={"approved": True},
        )

        self.assertEqual(report["execution_state"], "review_required")
        self.assertFalse(report["execution_allowed"])
        self.assertEqual(report["action_results"][0]["action_state"], "review_required")

    def test_raw_execute_flag_is_blocked(self) -> None:
        from core.runtime.governed_runtime_action_executor import build_governed_runtime_action_execution_report

        gateway = self._gateway(dry_run_only=False)
        gateway["action_requests"][0]["execute"] = True
        report = build_governed_runtime_action_execution_report(
            gateway_report=gateway,
            boundary_report=self._boundary(),
        )

        self.assertEqual(report["execution_state"], "blocked")
        self.assertIn("raw_execute_flag_forbidden", report["reason_codes"])

    def test_report_is_deterministic_and_does_not_mutate_inputs(self) -> None:
        from core.runtime.governed_runtime_action_executor import build_governed_runtime_action_execution_report

        gateway = self._gateway(state="dry_run_only", request_type="dry_run_repair", dry_run_only=True)
        boundary = self._boundary()
        gateway_before = copy.deepcopy(gateway)
        boundary_before = copy.deepcopy(boundary)

        first = build_governed_runtime_action_execution_report(
            gateway_report=gateway,
            boundary_report=boundary,
        )
        second = build_governed_runtime_action_execution_report(
            gateway_report=gateway,
            boundary_report=boundary,
        )

        self.assertEqual(first, second)
        self.assertEqual(gateway, gateway_before)
        self.assertEqual(boundary, boundary_before)


if __name__ == "__main__":
    unittest.main()
