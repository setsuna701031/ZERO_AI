from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class GovernedRuntimeReplaySessionTest(unittest.TestCase):
    def _session(self) -> dict:
        return {
            "schema_version": "governed_runtime_execution_session.v1",
            "execution_session_id": "session-1",
            "session_state": "checkpointed",
            "source_execution_id": "execution-1",
            "source_gateway_id": "gateway-1",
            "source_boundary_id": "boundary-1",
            "event_timeline": [
                {
                    "event_id": "event-1",
                    "event_type": "execution_report_received",
                    "event_state": "dry_run",
                    "source_ref": "execution-1",
                    "sequence": 0,
                    "payload": {},
                },
                {
                    "event_id": "event-2",
                    "event_type": "action_result",
                    "event_state": "dry_run",
                    "source_ref": "request-1",
                    "sequence": 1,
                    "payload": {},
                },
            ],
            "checkpoint_snapshots": [
                {
                    "checkpoint_id": "checkpoint-1",
                    "checkpoint_type": "execution_start",
                    "checkpoint_state": "captured",
                    "source_event_id": "event-1",
                    "runtime_state_ref": "execution-1",
                    "sequence": 0,
                    "payload": {},
                }
            ],
            "replay_order_valid": True,
            "rollback_eligible": True,
            "seal_handoff_ready": False,
            "continuation_contract": {"can_continue": True},
            "blocking_issues": [],
            "reason_codes": [],
        }

    def test_constants_are_stable(self) -> None:
        from core.runtime.governed_runtime_replay_session import (
            governed_runtime_replay_session_required_fields,
            governed_runtime_replay_session_states,
        )

        self.assertEqual(
            governed_runtime_replay_session_states(),
            [
                "prepared",
                "running",
                "consistent",
                "diverged",
                "rewind_required",
                "blocked",
                "failed",
            ],
        )
        self.assertEqual(
            governed_runtime_replay_session_required_fields(),
            [
                "replay_session_id",
                "source_execution_session_id",
                "replay_state",
                "timeline_replay_valid",
                "checkpoint_replay_valid",
                "rollback_replay_valid",
                "continuation_replay_valid",
                "forensic_replay_valid",
                "deterministic_resume_ready",
                "replay_events",
                "replay_checkpoints",
                "replay_divergences",
                "rewind_points",
                "blocking_issues",
                "reason_codes",
            ],
        )

    def test_builds_consistent_replay_from_session(self) -> None:
        from core.runtime.governed_runtime_replay_session import (
            build_governed_runtime_replay_session_report,
            validate_governed_runtime_replay_session_report,
        )

        report = build_governed_runtime_replay_session_report(
            execution_session_report=self._session()
        )
        validation = validate_governed_runtime_replay_session_report(report)

        self.assertTrue(report["replay_session_id"].startswith("governed-runtime-replay-session-"))
        self.assertEqual(report["source_execution_session_id"], "session-1")
        self.assertEqual(report["replay_state"], "consistent")
        self.assertTrue(report["timeline_replay_valid"])
        self.assertTrue(report["checkpoint_replay_valid"])
        self.assertTrue(report["deterministic_resume_ready"])
        self.assertEqual(report["replay_divergences"], [])
        self.assertTrue(validation["ok"])

    def test_timeline_divergence_creates_rewind_required(self) -> None:
        from core.runtime.governed_runtime_replay_session import (
            build_governed_runtime_replay_event,
            build_governed_runtime_replay_session_report,
        )

        replay_events = [
            build_governed_runtime_replay_event(
                replay_event_type="execution_report_received",
                replay_event_state="dry_run",
                source_event_id="wrong-event",
                sequence=0,
            ),
            build_governed_runtime_replay_event(
                replay_event_type="action_result",
                replay_event_state="dry_run",
                source_event_id="event-2",
                sequence=1,
            ),
        ]
        report = build_governed_runtime_replay_session_report(
            execution_session_report=self._session(),
            replay_events=replay_events,
        )

        self.assertEqual(report["replay_state"], "blocked")
        self.assertFalse(report["timeline_replay_valid"])
        self.assertIn("timeline_replay_invalid", report["reason_codes"])
        self.assertGreaterEqual(len(report["rewind_points"]), 1)

    def test_checkpoint_divergence_is_detected(self) -> None:
        from core.runtime.governed_runtime_replay_session import (
            build_governed_runtime_replay_checkpoint,
            build_governed_runtime_replay_session_report,
        )

        replay_checkpoints = [
            build_governed_runtime_replay_checkpoint(
                replay_checkpoint_type="execution_start",
                replay_checkpoint_state="changed",
                source_checkpoint_id="checkpoint-1",
                sequence=0,
            )
        ]
        report = build_governed_runtime_replay_session_report(
            execution_session_report=self._session(),
            replay_checkpoints=replay_checkpoints,
        )

        self.assertEqual(report["replay_state"], "blocked")
        self.assertFalse(report["checkpoint_replay_valid"])
        self.assertIn("checkpoint_replay_invalid", report["reason_codes"])

    def test_blocked_source_session_blocks_replay(self) -> None:
        from core.runtime.governed_runtime_replay_session import build_governed_runtime_replay_session_report

        session = self._session()
        session["session_state"] = "blocked"

        report = build_governed_runtime_replay_session_report(
            execution_session_report=session
        )

        self.assertEqual(report["replay_state"], "blocked")
        self.assertFalse(report["deterministic_resume_ready"])
        self.assertIn("source_execution_session_blocked", report["reason_codes"])

    def test_rollback_replay_mismatch_blocks(self) -> None:
        from core.runtime.governed_runtime_replay_session import build_governed_runtime_replay_session_report

        report = build_governed_runtime_replay_session_report(
            execution_session_report=self._session(),
            rollback_replay_report={"rollback_replay_valid": False},
        )

        self.assertEqual(report["replay_state"], "blocked")
        self.assertFalse(report["rollback_replay_valid"])
        self.assertIn("rollback_replay_invalid", report["reason_codes"])

    def test_continuation_replay_mismatch_blocks(self) -> None:
        from core.runtime.governed_runtime_replay_session import build_governed_runtime_replay_session_report

        report = build_governed_runtime_replay_session_report(
            execution_session_report=self._session(),
            continuation_replay_report={"continuation_replay_valid": False},
        )

        self.assertEqual(report["replay_state"], "blocked")
        self.assertFalse(report["continuation_replay_valid"])
        self.assertIn("continuation_replay_invalid", report["reason_codes"])

    def test_forensic_replay_source_mismatch_blocks(self) -> None:
        from core.runtime.governed_runtime_replay_session import build_governed_runtime_replay_session_report

        report = build_governed_runtime_replay_session_report(
            execution_session_report=self._session(),
            forensic_replay_report={
                "forensic_replay_valid": True,
                "source_execution_session_id": "other-session",
            },
        )

        self.assertEqual(report["replay_state"], "blocked")
        self.assertFalse(report["forensic_replay_valid"])
        self.assertIn("forensic_replay_invalid", report["reason_codes"])

    def test_summary_is_deterministic_and_does_not_mutate_inputs(self) -> None:
        from core.runtime.governed_runtime_replay_session import (
            build_governed_runtime_replay_session_report,
            build_governed_runtime_replay_session_summary,
        )

        session = self._session()
        before = copy.deepcopy(session)

        first = build_governed_runtime_replay_session_report(
            execution_session_report=session
        )
        second = build_governed_runtime_replay_session_report(
            execution_session_report=session
        )
        summary = build_governed_runtime_replay_session_summary(first)

        self.assertEqual(first, second)
        self.assertEqual(session, before)
        self.assertEqual(summary["replay_session_id"], first["replay_session_id"])
        self.assertEqual(summary["divergence_count"], len(first["replay_divergences"]))


if __name__ == "__main__":
    unittest.main()
