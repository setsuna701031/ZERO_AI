from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class GovernedRuntimeExecutionSessionTest(unittest.TestCase):
    def _action_execution(self, *, state: str = "dry_run") -> dict:
        return {
            "schema_version": "governed_runtime_action_executor.v1",
            "governed_action_execution_id": "execution-1",
            "source_gateway_id": "gateway-1",
            "source_boundary_id": "boundary-1",
            "execution_state": state,
            "execution_allowed": state == "completed",
            "dry_run_only": state == "dry_run",
            "approval_required": state == "review_required",
            "action_results": [
                {
                    "request_id": "request-1",
                    "request_type": "dry_run_repair" if state == "dry_run" else "no_action",
                    "action_state": state,
                    "execution_performed": False,
                    "reason_codes": [],
                    "blocking_issues": [],
                }
            ],
            "blocked_actions": [],
            "review_required_actions": [],
            "execution_summary": {},
            "blocking_issues": [],
            "reason_codes": [],
        }

    def _boundary(self, *, state: str = "boundary_ready") -> dict:
        return {
            "boundary_id": "boundary-1",
            "boundary_state": state,
            "execution_allowed": state == "boundary_ready",
            "reason_codes": [],
        }

    def _gateway(self, *, state: str = "dry_run_only") -> dict:
        return {
            "gateway_id": "gateway-1",
            "gateway_state": state,
            "input_readiness_id": "readiness-1",
            "reason_codes": [],
        }

    def test_constants_are_stable(self) -> None:
        from core.runtime.governed_runtime_execution_session import (
            governed_runtime_execution_session_required_fields,
            governed_runtime_execution_session_states,
        )

        self.assertEqual(
            governed_runtime_execution_session_states(),
            [
                "created",
                "prepared",
                "running",
                "checkpointed",
                "review_required",
                "blocked",
                "sealed",
                "rolled_back",
                "failed",
            ],
        )
        self.assertEqual(
            governed_runtime_execution_session_required_fields(),
            [
                "execution_session_id",
                "session_state",
                "source_execution_id",
                "source_gateway_id",
                "source_boundary_id",
                "event_timeline",
                "checkpoint_snapshots",
                "replay_order_valid",
                "rollback_eligible",
                "seal_handoff_ready",
                "continuation_contract",
                "blocking_issues",
                "reason_codes",
            ],
        )

    def test_builds_checkpointed_session_from_dry_run_execution(self) -> None:
        from core.runtime.governed_runtime_execution_session import (
            build_governed_runtime_execution_session_report,
            validate_governed_runtime_execution_session_report,
        )

        report = build_governed_runtime_execution_session_report(
            action_execution_report=self._action_execution(state="dry_run"),
            boundary_report=self._boundary(),
            gateway_report=self._gateway(),
        )
        validation = validate_governed_runtime_execution_session_report(report)

        self.assertTrue(report["execution_session_id"].startswith("governed-runtime-execution-session-"))
        self.assertEqual(report["session_state"], "checkpointed")
        self.assertEqual(report["source_execution_id"], "execution-1")
        self.assertEqual(report["source_gateway_id"], "gateway-1")
        self.assertEqual(report["source_boundary_id"], "boundary-1")
        self.assertTrue(report["replay_order_valid"])
        self.assertTrue(report["rollback_eligible"])
        self.assertFalse(report["seal_handoff_ready"])
        self.assertGreaterEqual(len(report["event_timeline"]), 1)
        self.assertGreaterEqual(len(report["checkpoint_snapshots"]), 1)
        self.assertTrue(validation["ok"])

    def test_review_required_session_is_not_continuable(self) -> None:
        from core.runtime.governed_runtime_execution_session import build_governed_runtime_execution_session_report

        report = build_governed_runtime_execution_session_report(
            action_execution_report=self._action_execution(state="review_required"),
            boundary_report=self._boundary(),
            gateway_report=self._gateway(state="approval_required"),
        )

        self.assertEqual(report["session_state"], "review_required")
        self.assertFalse(report["rollback_eligible"])
        self.assertTrue(report["continuation_contract"]["can_continue"])

    def test_blocked_boundary_blocks_session(self) -> None:
        from core.runtime.governed_runtime_execution_session import build_governed_runtime_execution_session_report

        report = build_governed_runtime_execution_session_report(
            action_execution_report=self._action_execution(state="dry_run"),
            boundary_report=self._boundary(state="blocked"),
            gateway_report=self._gateway(),
        )

        self.assertEqual(report["session_state"], "blocked")
        self.assertIn("source_boundary_blocked", report["reason_codes"])

    def test_seal_handoff_ready_creates_sealed_session(self) -> None:
        from core.runtime.governed_runtime_execution_session import build_governed_runtime_execution_session_report

        report = build_governed_runtime_execution_session_report(
            action_execution_report=self._action_execution(state="completed"),
            boundary_report=self._boundary(),
            gateway_report=self._gateway(state="ready"),
            seal_handoff={"seal_ready": True},
        )

        self.assertEqual(report["session_state"], "sealed")
        self.assertTrue(report["seal_handoff_ready"])

    def test_rollback_report_creates_rolled_back_session(self) -> None:
        from core.runtime.governed_runtime_execution_session import build_governed_runtime_execution_session_report

        report = build_governed_runtime_execution_session_report(
            action_execution_report=self._action_execution(state="completed"),
            boundary_report=self._boundary(),
            gateway_report=self._gateway(state="ready"),
            rollback_report={"rollback_performed": True},
        )

        self.assertEqual(report["session_state"], "rolled_back")
        self.assertTrue(report["rollback_eligible"])

    def test_replay_order_mismatch_blocks_session(self) -> None:
        from core.runtime.governed_runtime_execution_session import (
            build_governed_runtime_execution_event,
            build_governed_runtime_execution_checkpoint,
            build_governed_runtime_execution_session_report,
        )

        events = [
            build_governed_runtime_execution_event(
                event_type="manual",
                event_state="captured",
                source_ref="source-1",
                sequence=0,
            )
        ]
        checkpoints = [
            build_governed_runtime_execution_checkpoint(
                checkpoint_type="manual",
                checkpoint_state="captured",
                source_event_id="missing-event",
                runtime_state_ref="state-1",
                sequence=0,
            )
        ]
        report = build_governed_runtime_execution_session_report(
            action_execution_report=self._action_execution(state="dry_run"),
            boundary_report=self._boundary(),
            gateway_report=self._gateway(),
            event_timeline=events,
            checkpoint_snapshots=checkpoints,
        )

        self.assertEqual(report["session_state"], "blocked")
        self.assertFalse(report["replay_order_valid"])
        self.assertIn("session_replay_order_invalid", report["reason_codes"])

    def test_invalid_transition_blocks_session(self) -> None:
        from core.runtime.governed_runtime_execution_session import build_governed_runtime_execution_session_report

        report = build_governed_runtime_execution_session_report(
            action_execution_report=self._action_execution(state="completed"),
            boundary_report=self._boundary(),
            gateway_report=self._gateway(state="ready"),
            previous_session_state="sealed",
        )

        self.assertEqual(report["session_state"], "blocked")
        self.assertFalse(report["transition_valid"])
        self.assertIn("invalid_session_state_transition", report["reason_codes"])

    def test_summary_is_deterministic_and_does_not_mutate_inputs(self) -> None:
        from core.runtime.governed_runtime_execution_session import (
            build_governed_runtime_execution_session_report,
            build_governed_runtime_execution_session_summary,
        )

        action_execution = self._action_execution(state="dry_run")
        boundary = self._boundary()
        gateway = self._gateway()
        before = (copy.deepcopy(action_execution), copy.deepcopy(boundary), copy.deepcopy(gateway))

        first = build_governed_runtime_execution_session_report(
            action_execution_report=action_execution,
            boundary_report=boundary,
            gateway_report=gateway,
        )
        second = build_governed_runtime_execution_session_report(
            action_execution_report=action_execution,
            boundary_report=boundary,
            gateway_report=gateway,
        )
        summary = build_governed_runtime_execution_session_summary(first)

        self.assertEqual(first, second)
        self.assertEqual((action_execution, boundary, gateway), before)
        self.assertEqual(summary["execution_session_id"], first["execution_session_id"])
        self.assertEqual(summary["event_count"], len(first["event_timeline"]))


if __name__ == "__main__":
    unittest.main()
