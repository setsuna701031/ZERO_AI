from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeRecoveryExecutionReviewContractTest(unittest.TestCase):
    def _seal(self, seal_id: str = "recovery-execution-review"):
        from core.runtime.runtime_mainline_evidence_seal import build_runtime_mainline_evidence_seal

        return build_runtime_mainline_evidence_seal(
            workspace_root="workspace",
            seal_id=seal_id,
        )

    def _planner(self, **kwargs):
        from core.runtime.runtime_recovery_plan import RuntimeRecoveryPlanner

        return RuntimeRecoveryPlanner(**kwargs)

    def _builder(self):
        from core.runtime.runtime_recovery_execution_contract import RuntimeRecoveryExecutionContractBuilder

        return RuntimeRecoveryExecutionContractBuilder()

    def _reviewer(self):
        from core.runtime.runtime_recovery_execution_review import RuntimeRecoveryExecutionReviewer

        return RuntimeRecoveryExecutionReviewer()

    def _failed_summary(self, seal_id: str):
        planner = self._planner()
        summary = planner.policy_evaluator.reasoner.reconstructor.snapshot_builder.registry.query.summary_from(
            self._seal(seal_id)
        )
        summary["events"]["step_executor"] = {
            "count": 1,
            "phases": ["step_failure"],
            "statuses": ["failed"],
            "fingerprints": [f"{seal_id}:failed-fp"],
        }
        return summary

    def _approved_contract_report(self, seal_id: str):
        plan = self._planner().plan(self._failed_summary(seal_id))
        return self._builder().build(plan)

    def test_risk_review_reporting(self) -> None:
        review = self._reviewer().review(self._approved_contract_report("review-risk"))
        risk = review.risk_summary()

        self.assertEqual(risk["risk_profile"], "execution_contract_only")
        self.assertTrue(risk["all_executable_false"])
        self.assertTrue(risk["all_guards_ok"])
        self.assertEqual(risk["guard_failure_count"], 0)
        self.assertEqual(risk["executable_contract_count"], 0)

    def test_blocked_deferred_review_behavior(self) -> None:
        from core.runtime.runtime_recovery_policy import RuntimeRecoveryPolicyEvaluator

        strict_policy = RuntimeRecoveryPolicyEvaluator(
            replay_trust_threshold=101,
            replay_warn_threshold=90,
        )
        plan = self._planner(policy_evaluator=strict_policy).plan(
            self._seal("review-deferred")
        )
        contract_report = self._builder().build(plan)
        review = self._reviewer().review(contract_report)

        blocked_deferred = review.blocked_deferred_review()

        self.assertEqual(blocked_deferred["state"], "deferred")
        self.assertGreater(blocked_deferred["explanation_count"], 0)
        self.assertEqual(review.review_summary()["state"], "deferred")

    def test_confirmation_review_handling(self) -> None:
        review = self._reviewer().review(self._approved_contract_report("review-confirmation"))
        confirmation = review.confirmation_review()

        self.assertEqual(confirmation["state"], "ready_for_confirmation")
        self.assertEqual(confirmation["missing_confirmation_count"], 0)
        self.assertEqual(confirmation["executable_contract_count"], 0)
        self.assertEqual(confirmation["reason"], "confirmation_required_for_all_contracts")

    def test_deterministic_review_output(self) -> None:
        reviewer = self._reviewer()

        first = reviewer.review(self._approved_contract_report("review-deterministic"))
        second = reviewer.review(self._approved_contract_report("review-deterministic"))

        self.assertEqual(first.payload, second.payload)
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_replay_integrity_review_correctness(self) -> None:
        review = self._reviewer().review(self._approved_contract_report("review-replay"))
        replay = review.replay_integrity_review()

        self.assertEqual(replay["state"], "ready_for_confirmation")
        self.assertEqual(replay["reason"], "replay_integrity_review_passed")
        self.assertEqual(replay["replay_contract_count"], 1)
        self.assertEqual(replay["replay_safety"], ["replay_safe"])
        self.assertEqual(replay["trust_scores"], [100])

    def test_missing_evidence_safety(self) -> None:
        contract_report = self._builder().build(self._planner().plan(None))
        review = self._reviewer().review(contract_report)

        self.assertEqual(review.review_summary()["state"], "blocked")
        self.assertEqual(review.lineage_trust_review()["state"], "blocked")
        self.assertEqual(review.replay_integrity_review()["state"], "blocked")
        self.assertEqual(review.blocked_deferred_review()["state"], "blocked")
        self.assertTrue(review.blocked_deferred_review()["explanations"])

    def test_policy_reason_review(self) -> None:
        review = self._reviewer().review(self._approved_contract_report("review-policy-reason"))
        policy = review.policy_reason_review()

        self.assertEqual(policy["approval_state"], "approve")
        self.assertEqual(policy["approval_reason"], "recovery_plan_approval_granted")
        self.assertGreater(policy["reason_count"], 0)

    def test_review_report_is_immutable(self) -> None:
        review = self._reviewer().review(self._approved_contract_report("review-immutable"))

        payload = review.payload
        payload["read_only"] = False
        review.contract_reviews().append({"review_id": "polluted"})

        self.assertTrue(review.payload["read_only"])
        self.assertNotIn(
            "polluted",
            [item.get("review_id") for item in review.contract_reviews()],
        )


if __name__ == "__main__":
    unittest.main()
