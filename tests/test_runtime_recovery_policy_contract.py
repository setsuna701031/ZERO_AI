from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeRecoveryPolicyContractTest(unittest.TestCase):
    def _seal(self, seal_id: str = "recovery-policy"):
        from core.runtime.runtime_mainline_evidence_seal import build_runtime_mainline_evidence_seal

        return build_runtime_mainline_evidence_seal(
            workspace_root="workspace",
            seal_id=seal_id,
        )

    def _evaluator(self, **kwargs):
        from core.runtime.runtime_recovery_policy import RuntimeRecoveryPolicyEvaluator

        return RuntimeRecoveryPolicyEvaluator(**kwargs)

    def _reasoner(self):
        from core.runtime.runtime_recovery_reasoning import RuntimeRecoveryReasoner

        return RuntimeRecoveryReasoner()

    def _state_from_payload(self, payload):
        from core.runtime.runtime_evidence_replay_reconstruction import RuntimeEvidenceReplayState

        return RuntimeEvidenceReplayState(payload)

    def test_unsafe_lineage_blocks_policy(self) -> None:
        reasoner = self._reasoner()
        state = reasoner.reconstructor.reconstruct(self._seal("policy-unsafe-lineage"))
        payload = state.payload
        payload["lineage_replay"][2]["lineage_type"] = "audit"

        report = self._evaluator().evaluate(self._state_from_payload(payload))

        self.assertEqual(report.lineage_policy()["decision"], "block")
        self.assertEqual(report.lineage_policy()["reason"], "unsafe_lineage")
        self.assertEqual(report.replay_policy()["decision"], "block")
        self.assertEqual(report.rollback_policy()["decision"], "block")
        self.assertEqual(report.action_classification()["classification"], "block")

    def test_replay_trust_threshold_policy(self) -> None:
        evaluator = self._evaluator(replay_trust_threshold=101, replay_warn_threshold=90)
        report = evaluator.evaluate(self._seal("policy-threshold"))

        threshold = report.trust_threshold_policy()
        replay = report.replay_policy()

        self.assertEqual(threshold["decision"], "warn")
        self.assertEqual(threshold["score"], 100)
        self.assertEqual(threshold["required_score"], 101)
        self.assertEqual(replay["decision"], "warn")
        self.assertEqual(replay["reason"], "replay_allowed_with_policy_warning")

    def test_rollback_policy_classification(self) -> None:
        report = self._evaluator().evaluate(self._seal("policy-rollback"))

        rollback = report.rollback_policy()

        self.assertEqual(rollback["decision"], "allow")
        self.assertEqual(rollback["candidate_count"], 3)
        self.assertEqual(rollback["allowed_count"], 3)
        self.assertEqual(
            [candidate["decision"] for candidate in rollback["candidates"]],
            ["allow", "allow", "allow"],
        )
        self.assertTrue(all(candidate["action"] == "none" for candidate in rollback["candidates"]))

    def test_failed_execution_recovery_policy(self) -> None:
        evaluator = self._evaluator()
        summary = evaluator.reasoner.reconstructor.snapshot_builder.registry.query.summary_from(
            self._seal("policy-failed-execution")
        )
        summary["events"]["step_executor"] = {
            "count": 1,
            "phases": ["step_failure"],
            "statuses": ["failed"],
            "fingerprints": ["failed-policy-fp"],
        }

        report = evaluator.evaluate(summary)
        failed = report.failed_execution_policy()

        self.assertEqual(failed["decision"], "allow")
        self.assertEqual(failed["failed_execution_count"], 1)
        self.assertEqual(failed["candidate_count"], 1)
        self.assertEqual(failed["candidates"][0]["candidate_id"], "failed_execution:failed-policy-fp")
        self.assertEqual(failed["candidates"][0]["action"], "none")
        self.assertFalse(failed["candidates"][0]["executes_action"])

    def test_deterministic_policy_output(self) -> None:
        evaluator = self._evaluator()

        first = evaluator.evaluate(self._seal("policy-deterministic"))
        second = evaluator.evaluate(self._seal("policy-deterministic"))

        self.assertEqual(first.payload, second.payload)
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_missing_evidence_safety(self) -> None:
        report = self._evaluator().evaluate(None)

        self.assertEqual(report.lineage_policy()["decision"], "block")
        self.assertEqual(report.trust_threshold_policy()["decision"], "block")
        self.assertEqual(report.replay_policy()["decision"], "block")
        self.assertEqual(report.rollback_policy()["decision"], "block")
        self.assertEqual(report.failed_execution_policy()["decision"], "block")
        self.assertEqual(report.action_classification()["classification"], "block")
        self.assertEqual(report.rollback_policy()["candidate_count"], 0)

    def test_policy_report_is_immutable_and_does_not_mutate_reasoning(self) -> None:
        evaluator = self._evaluator()
        reasoning = evaluator.reasoner.reason(self._seal("policy-immutable"))
        before = copy.deepcopy(reasoning.payload)
        report = evaluator.evaluate(reasoning)

        payload = report.payload
        payload["read_only"] = False
        report.rollback_policy()["candidates"].append({"candidate_id": "polluted"})
        report.policy_decisions().append({"policy": "polluted"})

        self.assertEqual(reasoning.payload, before)
        self.assertTrue(report.payload["read_only"])
        self.assertNotIn(
            "polluted",
            [candidate.get("candidate_id") for candidate in report.rollback_policy()["candidates"]],
        )
        self.assertNotIn(
            "polluted",
            [decision.get("policy") for decision in report.policy_decisions()],
        )


if __name__ == "__main__":
    unittest.main()
