from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeRecoveryApprovalContractTest(unittest.TestCase):
    def _seal(self, seal_id: str = "recovery-approval"):
        from core.runtime.runtime_mainline_evidence_seal import build_runtime_mainline_evidence_seal

        return build_runtime_mainline_evidence_seal(
            workspace_root="workspace",
            seal_id=seal_id,
        )

    def _planner(self):
        from core.runtime.runtime_recovery_plan import RuntimeRecoveryPlanner

        return RuntimeRecoveryPlanner()

    def _evaluator(self):
        from core.runtime.runtime_recovery_approval import RuntimeRecoveryApprovalEvaluator

        return RuntimeRecoveryApprovalEvaluator()

    def _plan_from_payload(self, payload):
        from core.runtime.runtime_recovery_plan import RuntimeRecoveryPlanReport

        return RuntimeRecoveryPlanReport(payload)

    def _state_from_payload(self, payload):
        from core.runtime.runtime_evidence_replay_reconstruction import RuntimeEvidenceReplayState

        return RuntimeEvidenceReplayState(payload)

    def test_unsafe_recovery_rejection(self) -> None:
        planner = self._planner()
        state = planner.policy_evaluator.reasoner.reconstructor.reconstruct(
            self._seal("approval-unsafe-lineage")
        )
        payload = state.payload
        payload["lineage_replay"][2]["lineage_type"] = "audit"
        plan = planner.plan(self._state_from_payload(payload))

        approval = self._evaluator().evaluate(plan)

        self.assertEqual(approval.recovery_approval()["state"], "reject")
        self.assertEqual(
            approval.recovery_approval()["reason"],
            "unsafe_recovery_isolated_lineage",
        )
        self.assertEqual(approval.replay_approval()["state"], "reject")
        self.assertEqual(approval.rollback_approval()["state"], "reject")

    def test_policy_plan_mismatch_rejection(self) -> None:
        plan = self._planner().plan(self._seal("approval-policy-mismatch"))
        payload = plan.payload
        payload["rollback_plans"][0]["policy_decision"] = "block"

        approval = self._evaluator().evaluate(self._plan_from_payload(payload))

        self.assertEqual(approval.consistency_check()["state"], "reject")
        self.assertIn(
            "policy_plan_decision_mismatch",
            [issue["type"] for issue in approval.consistency_check()["issues"]],
        )
        self.assertEqual(approval.recovery_approval()["state"], "reject")

    def test_deterministic_approval_output(self) -> None:
        planner = self._planner()
        evaluator = self._evaluator()

        first = evaluator.evaluate(planner.plan(self._seal("approval-deterministic")))
        second = evaluator.evaluate(planner.plan(self._seal("approval-deterministic")))

        self.assertEqual(first.payload, second.payload)
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_replay_approval_gating(self) -> None:
        plan = self._planner().plan(self._seal("approval-replay"))
        approval = self._evaluator().evaluate(plan)

        replay = approval.replay_approval()

        self.assertEqual(replay["state"], "approve")
        self.assertEqual(replay["reason"], "replay_approval_granted")
        self.assertTrue(replay["approval_can_be_granted"])
        self.assertEqual(replay["action"], "none")
        self.assertFalse(replay["executes_action"])

    def test_rollback_approval_gating(self) -> None:
        plan = self._planner().plan(self._seal("approval-rollback"))
        approval = self._evaluator().evaluate(plan)

        rollback = approval.rollback_approval()

        self.assertEqual(rollback["state"], "approve")
        self.assertEqual(rollback["reason"], "rollback_approval_granted")
        self.assertEqual(rollback["plan_count"], 3)
        self.assertTrue(rollback["approval_can_be_granted"])
        self.assertEqual(rollback["action"], "none")

    def test_missing_evidence_safety(self) -> None:
        plan = self._planner().plan(None)
        approval = self._evaluator().evaluate(plan)

        self.assertEqual(approval.consistency_check()["state"], "approve")
        self.assertEqual(approval.recovery_approval()["state"], "reject")
        self.assertEqual(
            approval.recovery_approval()["reason"],
            "unsafe_recovery_isolated_lineage",
        )
        self.assertEqual(approval.replay_approval()["state"], "reject")
        self.assertEqual(approval.rollback_approval()["state"], "reject")
        self.assertTrue(approval.approval_reasons())

    def test_approval_report_is_immutable(self) -> None:
        plan = self._planner().plan(self._seal("approval-immutable"))
        approval = self._evaluator().evaluate(plan)

        payload = approval.payload
        payload["read_only"] = False
        approval.approval_reasons().append({"gate": "polluted"})

        self.assertTrue(approval.payload["read_only"])
        self.assertNotIn(
            "polluted",
            [reason.get("gate") for reason in approval.approval_reasons()],
        )


if __name__ == "__main__":
    unittest.main()
