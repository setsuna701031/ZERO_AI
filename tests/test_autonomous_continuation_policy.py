from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class AutonomousContinuationPolicyTest(unittest.TestCase):
    def _records(self, *, broken: bool = False, replay_divergent: bool = False) -> list[dict]:
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
        if replay_divergent:
            child["engineering_continuity"]["replay_id"] = "replay-1"
            child["engineering_continuity"]["repair_chain_id"] = "repair-1"
            child["engineering_continuity"]["execution_chain_depth"] = 2
        return [root, child]

    def _forensic_report(self, records: list[dict]) -> dict:
        from core.runtime.runtime_forensic_stack import build_runtime_forensic_report

        return build_runtime_forensic_report(records)

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

    def test_policy_constants_are_stable(self) -> None:
        from core.runtime.autonomous_continuation_policy import (
            ACTION_TYPES,
            CONTINUATION_STATES,
            POLICY_ID,
        )

        self.assertEqual(POLICY_ID, "autonomous_continuation_policy.v1")
        self.assertEqual(
            ACTION_TYPES,
            (
                "no_action",
                "needs_review",
                "repair_recommended",
                "replay_recommended",
                "planner_handoff_recommended",
                "blocked",
            ),
        )
        self.assertEqual(
            CONTINUATION_STATES,
            ("safe_to_continue", "needs_review", "blocked"),
        )

    def test_safe_forensic_report_recommends_no_action(self) -> None:
        from core.runtime.autonomous_continuation_policy import (
            build_autonomous_continuation_recommendation,
        )

        report = self._forensic_report(self._records())

        recommendation = build_autonomous_continuation_recommendation(report)

        self.assertEqual(recommendation["policy_id"], "autonomous_continuation_policy.v1")
        self.assertEqual(recommendation["input_report_id"], report["report_id"])
        self.assertEqual(recommendation["continuation_state"], "safe_to_continue")
        self.assertEqual(recommendation["blocking_issues"], [])
        self.assertEqual(recommendation["planner_handoff_payload"], {})
        self.assertEqual(recommendation["recommended_actions"][0]["action_type"], "no_action")
        self.assertEqual(recommendation["confidence"], 1.0)

    def test_detects_candidates_and_recommends_repair_handoff_for_broken_chain(self) -> None:
        from core.runtime.autonomous_continuation_policy import (
            build_autonomous_continuation_recommendation,
            classify_broken_chains,
            detect_continuation_candidates,
        )

        report = self._forensic_report(self._records(broken=True))

        candidates = detect_continuation_candidates(report)
        chain_classification = classify_broken_chains(report)
        recommendation = build_autonomous_continuation_recommendation(report)

        self.assertTrue(candidates["has_findings"])
        self.assertEqual(candidates["affected_repair_chain_ids"], ["repair-1"])
        self.assertIn("parent_session_id_not_found", candidates["reason_codes"])
        self.assertEqual(chain_classification["action_type"], "repair_recommended")
        self.assertEqual(chain_classification["continuation_state"], "needs_review")
        action_types = [item["action_type"] for item in recommendation["recommended_actions"]]
        self.assertIn("repair_recommended", action_types)
        self.assertIn("planner_handoff_recommended", action_types)
        self.assertFalse(recommendation["planner_handoff_payload"]["planner_invoked"])

    def test_classifies_replay_divergence_from_diff_report(self) -> None:
        from core.runtime.autonomous_continuation_policy import (
            classify_replay_divergence,
        )
        from core.runtime.runtime_replay_diff_comparator import (
            compare_replay_reconstruction_reports,
        )
        from core.runtime.runtime_replay_reconstruction_report import (
            build_runtime_replay_reconstruction_report,
        )

        baseline = build_runtime_replay_reconstruction_report(self._records())
        candidate = build_runtime_replay_reconstruction_report(self._records(replay_divergent=True))
        diff = compare_replay_reconstruction_reports(baseline, candidate)

        classification = classify_replay_divergence(diff)

        self.assertEqual(classification["action_type"], "replay_recommended")
        self.assertEqual(classification["continuation_state"], "needs_review")
        self.assertEqual(classification["affected_repair_chain_ids"], ["repair-1"])
        self.assertIn("added_timeline_entry", classification["reason_codes"])

    def test_landing_inconsistency_blocks_continuation(self) -> None:
        from core.runtime.autonomous_continuation_policy import (
            build_autonomous_continuation_recommendation,
            classify_execution_landing_inconsistencies,
        )

        contracts = self._landing_contracts()
        del contracts["replay"]["verification_result"]
        landing_classification = classify_execution_landing_inconsistencies(contracts)
        recommendation = build_autonomous_continuation_recommendation(
            self._forensic_report(self._records()),
            landing_consistency_report=contracts,
        )

        self.assertEqual(landing_classification["action_type"], "blocked")
        self.assertEqual(landing_classification["continuation_state"], "blocked")
        self.assertEqual(recommendation["continuation_state"], "blocked")
        self.assertEqual(recommendation["planner_handoff_payload"], {})
        self.assertIn("landing_missing_required_fields", recommendation["reason_codes"])

    def test_builds_planner_handoff_payload_without_invocation(self) -> None:
        from core.runtime.autonomous_continuation_policy import (
            build_planner_handoff_payload,
        )

        payload = build_planner_handoff_payload(
            [
                {
                    "action_type": "repair_recommended",
                    "reason_codes": ["missing_parent_ref"],
                    "affected_repair_chain_ids": ["repair-1"],
                }
            ],
            input_report_id="report-1",
        )

        self.assertEqual(payload["handoff_type"], "planner_handoff_recommended")
        self.assertFalse(payload["planner_invoked"])
        self.assertEqual(payload["input_report_id"], "report-1")
        self.assertEqual(payload["affected_repair_chain_ids"], ["repair-1"])

    def test_policy_does_not_mutate_inputs(self) -> None:
        from core.runtime.autonomous_continuation_policy import (
            build_autonomous_continuation_recommendation,
            classify_execution_landing_inconsistencies,
        )

        report = self._forensic_report(self._records(broken=True))
        contracts = self._landing_contracts()
        report_before = copy.deepcopy(report)
        contracts_before = copy.deepcopy(contracts)

        first = build_autonomous_continuation_recommendation(report)
        second = build_autonomous_continuation_recommendation(report)
        classify_execution_landing_inconsistencies(contracts)

        self.assertEqual(first, second)
        self.assertEqual(report, report_before)
        self.assertEqual(contracts, contracts_before)


if __name__ == "__main__":
    unittest.main()
