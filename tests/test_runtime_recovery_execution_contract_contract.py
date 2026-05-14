from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeRecoveryExecutionContractContractTest(unittest.TestCase):
    def _seal(self, seal_id: str = "recovery-execution-contract"):
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

    def _state_from_payload(self, payload):
        from core.runtime.runtime_evidence_replay_reconstruction import RuntimeEvidenceReplayState

        return RuntimeEvidenceReplayState(payload)

    def test_approved_plan_contract_generation(self) -> None:
        plan = self._planner().plan(self._failed_summary("contract-approved"))
        report = self._builder().build(plan)

        recovery = report.recovery_contract()
        summary = report.contract_summary()

        self.assertEqual(recovery["status"], "approved")
        self.assertEqual(recovery["approval_state"], "approve")
        self.assertFalse(recovery["executable"])
        self.assertTrue(recovery["requires_confirmation"])
        self.assertTrue(summary["all_executable_false"])
        self.assertTrue(summary["all_require_confirmation"])

    def test_rejected_approval_contract_blocking(self) -> None:
        planner = self._planner()
        state = planner.policy_evaluator.reasoner.reconstructor.reconstruct(
            self._seal("contract-rejected")
        )
        payload = state.payload
        payload["lineage_replay"][2]["lineage_type"] = "audit"
        plan = planner.plan(self._state_from_payload(payload))

        report = self._builder().build(plan)

        self.assertEqual(report.recovery_contract()["status"], "blocked")
        self.assertEqual(report.recovery_contract()["approval_state"], "reject")
        self.assertTrue(report.blocked_contracts())
        self.assertEqual(report.contract_summary()["approved_count"], 0)

    def test_deferred_approval_contract_handling(self) -> None:
        from core.runtime.runtime_recovery_policy import RuntimeRecoveryPolicyEvaluator

        strict_policy = RuntimeRecoveryPolicyEvaluator(
            replay_trust_threshold=101,
            replay_warn_threshold=90,
        )
        plan = self._planner(policy_evaluator=strict_policy).plan(
            self._seal("contract-deferred")
        )
        report = self._builder().build(plan)

        self.assertEqual(report.recovery_contract()["status"], "deferred")
        self.assertEqual(report.recovery_contract()["approval_state"], "defer")
        self.assertGreater(report.contract_summary()["deferred_count"], 0)
        self.assertTrue(report.blocked_contracts())

    def test_rollback_contract_metadata(self) -> None:
        plan = self._planner().plan(self._failed_summary("contract-rollback"))
        report = self._builder().build(plan)
        rollback_contracts = report.rollback_contracts()

        self.assertEqual(len(rollback_contracts), 3)
        first = rollback_contracts[0]

        self.assertEqual(first["contract_type"], "rollback")
        self.assertEqual(first["status"], "approved")
        self.assertFalse(first["executable"])
        self.assertTrue(first["requires_confirmation"])
        self.assertEqual(first["metadata"]["execution_id"], "step_executor.execute")
        self.assertIn("rollback_id", first["metadata"])
        self.assertTrue(first["risk"]["guards"]["no_rollback_execution"])

    def test_replay_contract_metadata(self) -> None:
        plan = self._planner().plan(self._failed_summary("contract-replay"))
        report = self._builder().build(plan)
        replay_contracts = report.replay_contracts()

        self.assertEqual(len(replay_contracts), 1)
        replay = replay_contracts[0]

        self.assertEqual(replay["contract_type"], "replay")
        self.assertEqual(replay["status"], "approved")
        self.assertEqual(replay["metadata"]["replay_safety"], "replay_safe")
        self.assertEqual(replay["metadata"]["trust_score"], 100)
        self.assertTrue(replay["risk"]["guards"]["no_runtime_execution"])

    def test_deterministic_contract_output(self) -> None:
        planner = self._planner()
        builder = self._builder()

        first = builder.build(planner.plan(self._failed_summary("contract-deterministic")))
        second = builder.build(planner.plan(self._failed_summary("contract-deterministic")))

        self.assertEqual(first.payload, second.payload)
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_missing_evidence_safety(self) -> None:
        plan = self._planner().plan(None)
        report = self._builder().build(plan)

        self.assertEqual(report.recovery_contract()["status"], "blocked")
        self.assertEqual(report.recovery_contract()["approval_state"], "reject")
        self.assertEqual(report.replay_contracts(), [])
        self.assertEqual(report.rollback_contracts(), [])
        self.assertEqual(report.failed_execution_contracts(), [])
        self.assertTrue(report.blocked_contracts())
        self.assertTrue(report.contract_summary()["all_executable_false"])

    def test_contract_report_is_immutable(self) -> None:
        report = self._builder().build(
            self._planner().plan(self._failed_summary("contract-immutable"))
        )

        payload = report.payload
        payload["read_only"] = False
        report.rollback_contracts().append({"contract_id": "polluted"})

        self.assertTrue(report.payload["read_only"])
        self.assertNotIn(
            "polluted",
            [contract.get("contract_id") for contract in report.rollback_contracts()],
        )


if __name__ == "__main__":
    unittest.main()
