from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeRecoveryPlanContractTest(unittest.TestCase):
    def _seal(self, seal_id: str = "recovery-plan"):
        from core.runtime.runtime_mainline_evidence_seal import build_runtime_mainline_evidence_seal

        return build_runtime_mainline_evidence_seal(
            workspace_root="workspace",
            seal_id=seal_id,
        )

    def _planner(self):
        from core.runtime.runtime_recovery_plan import RuntimeRecoveryPlanner

        return RuntimeRecoveryPlanner()

    def _state_from_payload(self, payload):
        from core.runtime.runtime_evidence_replay_reconstruction import RuntimeEvidenceReplayState

        return RuntimeEvidenceReplayState(payload)

    def test_rollback_plan_generation(self) -> None:
        report = self._planner().plan(self._seal("plan-rollback"))
        rollback_plans = report.rollback_plans()

        self.assertEqual(len(rollback_plans), 3)
        self.assertEqual(
            [plan["execution_id"] for plan in rollback_plans],
            ["step_executor.execute", "task_runtime.lifecycle", "scheduler.dispatch"],
        )
        self.assertEqual(
            [plan["replay_order"] for plan in rollback_plans],
            [0, 1, 2],
        )
        self.assertTrue(all(plan["action"] == "none" for plan in rollback_plans))
        self.assertTrue(all(not plan["executes_action"] for plan in rollback_plans))

    def test_replay_sequencing_correctness(self) -> None:
        report = self._planner().plan(self._seal("plan-sequence"))
        sequence = report.recovery_sequence()

        self.assertEqual(
            [item["sequence_order"] for item in sequence],
            list(range(len(sequence))),
        )
        self.assertEqual(sequence[0]["stage_type"], "replay_reconstruction")
        self.assertEqual(
            [item["stage_type"] for item in sequence],
            ["replay_reconstruction", "rollback", "rollback", "rollback"],
        )
        self.assertTrue(all(item["action"] == "none" for item in sequence))
        self.assertTrue(all(not item["executes_action"] for item in sequence))

    def test_unsafe_lineage_isolation_planning(self) -> None:
        planner = self._planner()
        state = planner.policy_evaluator.reasoner.reconstructor.reconstruct(
            self._seal("plan-unsafe-lineage")
        )
        payload = state.payload
        payload["lineage_replay"][2]["lineage_type"] = "audit"

        report = planner.plan(self._state_from_payload(payload))
        isolation_plans = report.lineage_isolation_plans()

        self.assertEqual(len(isolation_plans), 1)
        self.assertEqual(isolation_plans[0]["classification"], "unsafe_lineage_isolation_plan")
        self.assertEqual(isolation_plans[0]["policy_decision"], "block")
        self.assertEqual(report.rollback_plans(), [])
        self.assertEqual(report.replay_reconstruction_plans(), [])
        self.assertEqual(report.recovery_sequence()[0]["stage_type"], "lineage_isolation")

    def test_deterministic_recovery_planning(self) -> None:
        planner = self._planner()

        first = planner.plan(self._seal("plan-deterministic"))
        second = planner.plan(self._seal("plan-deterministic"))

        self.assertEqual(first.payload, second.payload)
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_immutable_plan_behavior(self) -> None:
        planner = self._planner()
        policy = planner.policy_evaluator.evaluate(self._seal("plan-immutable"))
        before = copy.deepcopy(policy.payload)
        report = planner.plan(policy)

        payload = report.payload
        payload["read_only"] = False
        report.rollback_plans().append({"plan_id": "polluted"})
        report.recovery_sequence().append({"plan_id": "polluted"})

        self.assertEqual(policy.payload, before)
        self.assertTrue(report.payload["read_only"])
        self.assertNotIn(
            "polluted",
            [plan.get("plan_id") for plan in report.rollback_plans()],
        )
        self.assertNotIn(
            "polluted",
            [item.get("plan_id") for item in report.recovery_sequence()],
        )

    def test_missing_evidence_safety(self) -> None:
        report = self._planner().plan(None)

        self.assertEqual(report.rollback_plans(), [])
        self.assertEqual(report.replay_reconstruction_plans(), [])
        self.assertEqual(report.failed_execution_plans(), [])
        self.assertEqual(len(report.lineage_isolation_plans()), 1)
        self.assertEqual(
            report.lineage_isolation_plans()[0]["classification"],
            "missing_evidence_isolation_plan",
        )
        self.assertEqual(
            [item["stage_type"] for item in report.recovery_sequence()],
            ["lineage_isolation"],
        )

    def test_failed_execution_recovery_plan_generation(self) -> None:
        planner = self._planner()
        summary = planner.policy_evaluator.reasoner.reconstructor.snapshot_builder.registry.query.summary_from(
            self._seal("plan-failed-execution")
        )
        summary["events"]["step_executor"] = {
            "count": 1,
            "phases": ["step_failure"],
            "statuses": ["failed"],
            "fingerprints": ["failed-plan-fp"],
        }

        report = planner.plan(summary)
        failed_plans = report.failed_execution_plans()

        self.assertEqual(len(failed_plans), 1)
        self.assertEqual(failed_plans[0]["failed_execution_id"], "failed-plan-fp")
        self.assertEqual(failed_plans[0]["policy_decision"], "allow")
        self.assertTrue(
            any(item["stage_type"] == "failed_execution_recovery" for item in report.recovery_sequence())
        )


if __name__ == "__main__":
    unittest.main()
