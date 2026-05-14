from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeRecoveryCommitGateContractTest(unittest.TestCase):
    def _seal(self, seal_id: str = "recovery-commit-gate"):
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

    def _executor(self):
        from core.runtime.runtime_recovery_dry_run_executor import RuntimeRecoveryDryRunExecutor

        return RuntimeRecoveryDryRunExecutor()

    def _gate(self):
        from core.runtime.runtime_recovery_commit_gate import RuntimeRecoveryCommitGate

        return RuntimeRecoveryCommitGate()

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

    def _approved_dry_run(self, seal_id: str):
        contract_report = self._builder().build(
            self._planner().plan(self._failed_summary(seal_id))
        )
        return self._executor().dry_run(contract_report)

    def test_dry_run_approval_gating(self) -> None:
        report = self._gate().evaluate(
            self._approved_dry_run("commit-gate-approved"),
            manual_confirmation_provided=True,
        )

        self.assertEqual(report.dry_run_commit_authorization()["state"], "commit_allowed")
        self.assertTrue(report.dry_run_commit_authorization()["commit_allowed"])
        self.assertTrue(report.rollback_commit_gate()["commit_allowed"])
        self.assertTrue(report.replay_commit_gate()["commit_allowed"])
        self.assertTrue(report.final_execution_readiness()["commit_allowed"])
        self.assertFalse(report.final_execution_readiness()["executes_recovery"])
        self.assertFalse(report.payload["executes_rollback"])
        self.assertFalse(report.payload["executes_repair"])

    def test_unsafe_simulation_blocking(self) -> None:
        from core.runtime.runtime_recovery_dry_run_executor import RuntimeRecoveryDryRunReport

        payload = self._approved_dry_run("commit-gate-unsafe").payload
        payload["sequence_simulation"][0]["would_execute"] = True
        unsafe_report = RuntimeRecoveryDryRunReport(payload)

        report = self._gate().evaluate(
            unsafe_report,
            manual_confirmation_provided=True,
        )

        unsafe = report.unsafe_simulation_rejection()
        self.assertEqual(unsafe["state"], "commit_blocked")
        self.assertTrue(unsafe["rejected"])
        self.assertFalse(report.final_execution_readiness()["commit_allowed"])
        self.assertIn("unsafe_simulation", unsafe["violations"][0])

    def test_confirmation_enforcement(self) -> None:
        gate = self._gate()
        dry_run = self._approved_dry_run("commit-gate-confirmation")

        without_confirmation = gate.evaluate(dry_run)
        with_confirmation = gate.evaluate(
            dry_run,
            manual_confirmation_provided=True,
        )

        self.assertTrue(without_confirmation.confirmation_enforcement()["requires_manual_confirmation"])
        self.assertFalse(without_confirmation.confirmation_enforcement()["commit_allowed"])
        self.assertFalse(without_confirmation.final_execution_readiness()["commit_allowed"])
        self.assertFalse(with_confirmation.confirmation_enforcement()["requires_manual_confirmation"])
        self.assertTrue(with_confirmation.confirmation_enforcement()["commit_allowed"])
        self.assertTrue(with_confirmation.final_execution_readiness()["commit_allowed"])

    def test_deterministic_gate_output(self) -> None:
        gate = self._gate()
        dry_run = self._approved_dry_run("commit-gate-deterministic")

        first = gate.evaluate(dry_run, manual_confirmation_provided=True)
        second = gate.evaluate(dry_run, manual_confirmation_provided=True)

        self.assertEqual(first.payload, second.payload)
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_blocked_deferred_propagation(self) -> None:
        from core.runtime.runtime_recovery_policy import RuntimeRecoveryPolicyEvaluator

        strict_policy = RuntimeRecoveryPolicyEvaluator(
            replay_trust_threshold=101,
            replay_warn_threshold=90,
        )
        contract_report = self._builder().build(
            self._planner(policy_evaluator=strict_policy).plan(
                self._seal("commit-gate-deferred")
            )
        )
        dry_run = self._executor().dry_run(contract_report)

        report = self._gate().evaluate(
            dry_run,
            manual_confirmation_provided=True,
        )

        propagated = report.blocked_deferred_propagation()
        self.assertEqual(propagated["state"], "commit_deferred")
        self.assertGreater(propagated["deferred_count"], 0)
        self.assertFalse(report.final_execution_readiness()["commit_allowed"])
        self.assertEqual(report.commit_summary()["state"], "commit_blocked")

    def test_missing_evidence_safety(self) -> None:
        from core.runtime.runtime_recovery_dry_run_executor import RuntimeRecoveryDryRunReport

        report = self._gate().evaluate(
            RuntimeRecoveryDryRunReport({}),
            manual_confirmation_provided=True,
        )

        self.assertEqual(report.dry_run_commit_authorization()["state"], "commit_blocked")
        self.assertTrue(report.dry_run_commit_authorization()["missing_evidence"])
        self.assertFalse(report.rollback_commit_gate()["commit_allowed"])
        self.assertFalse(report.replay_commit_gate()["commit_allowed"])
        self.assertFalse(report.final_execution_readiness()["commit_allowed"])

    def test_commit_gate_report_is_immutable(self) -> None:
        report = self._gate().evaluate(
            self._approved_dry_run("commit-gate-immutable"),
            manual_confirmation_provided=True,
        )

        payload = report.payload
        payload["read_only"] = False
        report.replay_commit_gate()["commit_allowed"] = False

        self.assertTrue(report.payload["read_only"])
        self.assertTrue(report.replay_commit_gate()["commit_allowed"])


if __name__ == "__main__":
    unittest.main()
