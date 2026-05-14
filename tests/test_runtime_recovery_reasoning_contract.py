from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeRecoveryReasoningContractTest(unittest.TestCase):
    def _seal(self, seal_id: str = "recovery-reasoning"):
        from core.runtime.runtime_mainline_evidence_seal import build_runtime_mainline_evidence_seal

        return build_runtime_mainline_evidence_seal(
            workspace_root="workspace",
            seal_id=seal_id,
        )

    def _reasoner(self):
        from core.runtime.runtime_recovery_reasoning import RuntimeRecoveryReasoner

        return RuntimeRecoveryReasoner()

    def _state_from_payload(self, payload):
        from core.runtime.runtime_evidence_replay_reconstruction import RuntimeEvidenceReplayState

        return RuntimeEvidenceReplayState(payload)

    def test_replay_trust_classification(self) -> None:
        reasoner = self._reasoner()
        report = reasoner.reason(self._seal("trust-classification"))

        replay_trust = report.replay_trust()
        replay_safety = report.replay_safety()

        self.assertEqual(replay_trust["classification"], "trusted")
        self.assertTrue(replay_trust["trusted"])
        self.assertEqual(replay_safety["classification"], "replay_safe")
        self.assertTrue(replay_safety["safe"])

    def test_rollback_candidate_reasoning(self) -> None:
        reasoner = self._reasoner()
        report = reasoner.reason(self._seal("rollback-candidates"))

        candidates = report.rollback_candidates()

        self.assertEqual(
            [candidate["execution_id"] for candidate in candidates],
            ["step_executor.execute", "task_runtime.lifecycle", "scheduler.dispatch"],
        )
        self.assertTrue(all(candidate["action"] == "none" for candidate in candidates))
        self.assertTrue(all(candidate["reasoning_only"] for candidate in candidates))
        self.assertEqual(
            {candidate["classification"] for candidate in candidates},
            {"rollback_candidate"},
        )

    def test_failed_execution_recovery_reasoning(self) -> None:
        reasoner = self._reasoner()
        summary = reasoner.reconstructor.snapshot_builder.registry.query.summary_from(
            self._seal("failed-execution-reasoning")
        )
        summary["events"]["step_executor"] = {
            "count": 1,
            "phases": ["step_failure"],
            "statuses": ["failed"],
            "fingerprints": ["failed-step-fp"],
        }

        report = reasoner.reason(summary)
        failed = report.failed_execution_recovery()

        self.assertEqual(failed["classification"], "failed_execution_replay_candidates")
        self.assertEqual(failed["candidate_count"], 1)
        self.assertEqual(failed["candidates"][0]["failed_execution_id"], "failed-step-fp")
        self.assertEqual(failed["candidates"][0]["action"], "none")
        self.assertTrue(failed["candidates"][0]["safe_to_consider"])

    def test_lineage_trust_analysis(self) -> None:
        reasoner = self._reasoner()
        report = reasoner.reason(self._seal("lineage-trust"))

        lineage = report.lineage_trust()

        self.assertEqual(lineage["classification"], "trusted")
        self.assertTrue(lineage["complete"])
        self.assertTrue(lineage["ordered"])
        self.assertEqual(
            lineage["actual_types"],
            ["plan", "snapshot", "replay", "audit", "bundle"],
        )

    def test_deterministic_reasoning_output(self) -> None:
        reasoner = self._reasoner()

        first = reasoner.reason(self._seal("deterministic-reasoning"))
        second = reasoner.reason(self._seal("deterministic-reasoning"))

        self.assertEqual(first.payload, second.payload)
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_missing_evidence_safety(self) -> None:
        report = self._reasoner().reason(None)

        replay_trust = report.replay_trust()
        replay_safety = report.replay_safety()

        self.assertEqual(replay_trust["classification"], "missing_evidence")
        self.assertEqual(replay_safety["classification"], "replay_unsafe_missing_evidence")
        self.assertFalse(replay_safety["safe"])
        self.assertEqual(report.rollback_candidates(), [])
        self.assertEqual(report.recovery_candidates(), [])

    def test_invalid_lineage_blocks_replay_safety(self) -> None:
        reasoner = self._reasoner()
        state = reasoner.reconstructor.reconstruct(self._seal("unsafe-lineage"))
        payload = state.payload
        payload["lineage_replay"][2]["lineage_type"] = "audit"

        report = reasoner.reason(self._state_from_payload(payload))

        self.assertEqual(report.lineage_trust()["classification"], "untrusted")
        self.assertEqual(report.replay_safety()["classification"], "replay_unsafe")
        self.assertFalse(report.replay_safety()["safe"])
        self.assertEqual(report.rollback_candidates(), [])

    def test_reasoning_report_is_immutable_and_does_not_mutate_replay(self) -> None:
        reasoner = self._reasoner()
        state = reasoner.reconstructor.reconstruct(self._seal("immutable-reasoning"))
        before = copy.deepcopy(state.payload)
        report = reasoner.reason(state)

        payload = report.payload
        payload["read_only"] = False
        report.rollback_candidates().append({"candidate_id": "polluted"})
        report.failed_execution_recovery()["classification"] = "polluted"

        self.assertEqual(state.payload, before)
        self.assertTrue(report.payload["read_only"])
        self.assertNotIn(
            "polluted",
            [candidate.get("candidate_id") for candidate in report.rollback_candidates()],
        )
        self.assertNotEqual(
            report.failed_execution_recovery().get("classification"),
            "polluted",
        )


if __name__ == "__main__":
    unittest.main()
