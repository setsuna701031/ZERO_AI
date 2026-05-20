from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class CrossSessionEngineeringContinuityTest(unittest.TestCase):
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

    def _landing_contracts(self) -> dict:
        base = {
            "task_id": "task-1",
            "session_id": "session-1",
            "status": "finished",
            "execution_result": {"ok": True},
            "verification_result": {"ok": True},
            "rollback_result": {"needed": False},
            "audit_ref": "audit-1",
            "evidence_ref": "evidence-1",
        }
        return {
            "self_edit": {**base, "task_id": "self-edit"},
            "repair": {**base, "task_id": "repair", "repair_chain_id": "repair-1"},
            "replay": {**base, "task_id": "replay", "replay_ref": "replay-1"},
            "mutation": {**base, "task_id": "mutation"},
        }

    def test_required_fields_are_stable(self) -> None:
        from core.runtime.cross_session_engineering_continuity import (
            HANDOFF_POLICY_ID,
            cross_session_handoff_required_fields,
        )

        self.assertEqual(HANDOFF_POLICY_ID, "cross_session_engineering_continuity.v1")
        self.assertEqual(
            cross_session_handoff_required_fields(),
            [
                "handoff_id",
                "source_session_id",
                "source_report_id",
                "continuation_state",
                "recommended_actions",
                "blocking_issues",
                "affected_repair_chain_ids",
                "next_session_startup_hints",
                "planner_handoff_payload",
                "handoff_valid",
                "reason_codes",
            ],
        )

    def test_summarizes_previous_session_engineering_state(self) -> None:
        from core.runtime.cross_session_engineering_continuity import (
            summarize_previous_session_engineering_state,
        )

        report = self._forensic_report(broken=True)

        summary = summarize_previous_session_engineering_state(report)

        self.assertEqual(summary["source_session_id"], "child")
        self.assertEqual(summary["source_report_id"], report["report_id"])
        self.assertEqual(summary["session_count"], 2)
        self.assertEqual(summary["affected_repair_chain_ids"], ["repair-1"])
        self.assertEqual(summary["chain_break_count"], 1)

    def test_builds_safe_cross_session_handoff_from_forensic_report(self) -> None:
        from core.runtime.cross_session_engineering_continuity import (
            build_cross_session_handoff_payload,
            validate_cross_session_handoff_payload,
        )

        report = self._forensic_report()

        handoff = build_cross_session_handoff_payload(
            source_session_id="session-source",
            forensic_report=report,
        )
        validation = validate_cross_session_handoff_payload(handoff)

        self.assertTrue(handoff["handoff_id"].startswith("cross-session-handoff-"))
        self.assertEqual(handoff["source_session_id"], "session-source")
        self.assertEqual(handoff["source_report_id"], report["report_id"])
        self.assertEqual(handoff["continuation_state"], "safe_to_continue")
        self.assertEqual(handoff["recommended_actions"][0]["action_type"], "no_action")
        self.assertEqual(handoff["planner_handoff_payload"], {})
        self.assertTrue(handoff["handoff_valid"])
        self.assertTrue(validation["ok"])

    def test_preserves_policy_recommendation_fields_and_planner_payload_as_data(self) -> None:
        from core.runtime.autonomous_continuation_policy import (
            build_autonomous_continuation_recommendation,
        )
        from core.runtime.cross_session_engineering_continuity import (
            build_cross_session_handoff_payload,
        )

        report = self._forensic_report(broken=True)
        recommendation = build_autonomous_continuation_recommendation(report)

        handoff = build_cross_session_handoff_payload(
            source_session_id="source-1",
            forensic_report=report,
            continuation_recommendation=recommendation,
        )

        self.assertEqual(handoff["continuation_state"], recommendation["continuation_state"])
        self.assertEqual(handoff["recommended_actions"], recommendation["recommended_actions"])
        self.assertEqual(handoff["blocking_issues"], recommendation["blocking_issues"])
        self.assertEqual(handoff["affected_repair_chain_ids"], ["repair-1"])
        self.assertEqual(handoff["reason_codes"], recommendation["reason_codes"])
        self.assertEqual(handoff["planner_handoff_payload"]["planner_invoked"], False)
        self.assertEqual(handoff["planner_handoff_payload"]["source_session_id"], "source-1")
        hint_types = [item["hint_type"] for item in handoff["next_session_startup_hints"]]
        self.assertIn("review_recommended_actions_before_continuation", hint_types)
        self.assertIn("preserve_repair_chain_context", hint_types)

    def test_landing_inconsistency_blocks_cross_session_handoff(self) -> None:
        from core.runtime.cross_session_engineering_continuity import (
            build_cross_session_handoff_payload,
        )

        contracts = self._landing_contracts()
        del contracts["replay"]["verification_result"]

        handoff = build_cross_session_handoff_payload(
            source_session_id="source-1",
            forensic_report=self._forensic_report(),
            landing_consistency_report=contracts,
        )

        self.assertEqual(handoff["continuation_state"], "blocked")
        self.assertEqual(handoff["planner_handoff_payload"], {})
        self.assertTrue(handoff["blocking_issues"])
        self.assertIn("landing_missing_required_fields", handoff["reason_codes"])
        hint_types = [item["hint_type"] for item in handoff["next_session_startup_hints"]]
        self.assertIn("resolve_blocking_issues_before_continuation", hint_types)

    def test_generates_planner_handoff_payload_without_invocation(self) -> None:
        from core.runtime.cross_session_engineering_continuity import (
            build_cross_session_planner_handoff_payload,
        )

        payload = build_cross_session_planner_handoff_payload(
            {
                "input_report_id": "report-1",
                "continuation_state": "needs_review",
                "recommended_actions": [
                    {
                        "action_type": "repair_recommended",
                        "reason_codes": ["missing_parent_ref"],
                        "affected_repair_chain_ids": ["repair-1"],
                    }
                ],
                "affected_repair_chain_ids": ["repair-1"],
            },
            source_session_id="source-1",
        )

        self.assertEqual(payload["handoff_type"], "planner_handoff_recommended")
        self.assertFalse(payload["planner_invoked"])
        self.assertEqual(payload["source_session_id"], "source-1")
        self.assertEqual(payload["affected_repair_chain_ids"], ["repair-1"])

    def test_validates_handoff_payload_shape(self) -> None:
        from core.runtime.cross_session_engineering_continuity import (
            validate_cross_session_handoff_payload,
        )

        invalid = validate_cross_session_handoff_payload(
            {
                "handoff_id": "handoff-1",
                "source_session_id": "source-1",
                "source_report_id": "report-1",
                "continuation_state": "continue_now",
                "recommended_actions": {},
                "blocking_issues": [],
                "affected_repair_chain_ids": [],
                "next_session_startup_hints": [],
                "planner_handoff_payload": {"planner_invoked": True},
                "handoff_valid": True,
                "reason_codes": [],
            }
        )
        missing = validate_cross_session_handoff_payload({})

        self.assertFalse(invalid["ok"])
        self.assertEqual(
            [item["field"] for item in invalid["invalid_fields"]],
            [
                "continuation_state",
                "recommended_actions",
                "planner_handoff_payload",
            ],
        )
        self.assertFalse(missing["ok"])
        self.assertIn("handoff_id", missing["missing_fields"])

    def test_handoff_builder_is_stable_and_does_not_mutate_inputs(self) -> None:
        from core.runtime.autonomous_continuation_policy import (
            build_autonomous_continuation_recommendation,
        )
        from core.runtime.cross_session_engineering_continuity import (
            build_cross_session_handoff_payload,
        )

        report = self._forensic_report(broken=True)
        recommendation = build_autonomous_continuation_recommendation(report)
        report_before = copy.deepcopy(report)
        recommendation_before = copy.deepcopy(recommendation)

        first = build_cross_session_handoff_payload(
            source_session_id="source-1",
            forensic_report=report,
            continuation_recommendation=recommendation,
        )
        second = build_cross_session_handoff_payload(
            source_session_id="source-1",
            forensic_report=report,
            continuation_recommendation=recommendation,
        )

        self.assertEqual(first, second)
        self.assertEqual(report, report_before)
        self.assertEqual(recommendation, recommendation_before)


if __name__ == "__main__":
    unittest.main()
