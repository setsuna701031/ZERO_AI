from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeRecoveryDryRunExecutorContractTest(unittest.TestCase):
    def _seal(self, seal_id: str = "recovery-dry-run"):
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
        return self._builder().build(self._planner().plan(self._failed_summary(seal_id)))

    def test_rollback_dry_run_simulation(self) -> None:
        report = self._executor().dry_run(self._approved_contract_report("dry-run-rollback"))
        rollback = report.rollback_dry_runs()

        self.assertEqual(len(rollback), 3)
        self.assertEqual(
            [item["metadata"]["execution_id"] for item in rollback],
            ["step_executor.execute", "task_runtime.lifecycle", "scheduler.dispatch"],
        )
        self.assertTrue(all(item["status"] == "simulated" for item in rollback))
        self.assertTrue(all(item["simulated_action"] == "simulate_rollback_sequence" for item in rollback))
        self.assertTrue(all(not item["would_execute"] for item in rollback))

    def test_replay_sequencing_simulation(self) -> None:
        report = self._executor().dry_run(self._approved_contract_report("dry-run-sequence"))
        sequence = report.sequence_simulation()

        self.assertEqual(
            [item["sequence_order"] for item in sequence],
            list(range(len(sequence))),
        )
        self.assertEqual(sequence[0]["stage_type"], "replay")
        self.assertIn("rollback", [item["stage_type"] for item in sequence])
        self.assertTrue(all(not item["executes_action"] for item in sequence))

    def test_blocked_deferred_dry_run_handling(self) -> None:
        from core.runtime.runtime_recovery_policy import RuntimeRecoveryPolicyEvaluator

        strict_policy = RuntimeRecoveryPolicyEvaluator(
            replay_trust_threshold=101,
            replay_warn_threshold=90,
        )
        contract_report = self._builder().build(
            self._planner(policy_evaluator=strict_policy).plan(self._seal("dry-run-deferred"))
        )
        report = self._executor().dry_run(contract_report)

        self.assertEqual(report.dry_run_summary()["status"], "deferred")
        self.assertTrue(report.blocked_deferred_dry_runs())
        self.assertTrue(
            any(item["status"] == "deferred" for item in report.blocked_deferred_dry_runs())
        )

    def test_confirmation_simulation_behavior(self) -> None:
        report = self._executor().dry_run(self._approved_contract_report("dry-run-confirmation"))
        confirmation = report.confirmation_simulation()

        self.assertEqual(confirmation["status"], "simulated")
        self.assertTrue(confirmation["confirmation_ready"])
        self.assertEqual(confirmation["missing_confirmation_count"], 0)
        self.assertEqual(confirmation["simulated_action"], "simulate_confirmation_gate")
        self.assertFalse(confirmation["executes_action"])

    def test_deterministic_dry_run_output(self) -> None:
        executor = self._executor()

        first = executor.dry_run(self._approved_contract_report("dry-run-deterministic"))
        second = executor.dry_run(self._approved_contract_report("dry-run-deterministic"))

        self.assertEqual(first.payload, second.payload)
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_missing_evidence_safety(self) -> None:
        contract_report = self._builder().build(self._planner().plan(None))
        report = self._executor().dry_run(contract_report)

        self.assertEqual(report.dry_run_summary()["status"], "blocked")
        self.assertEqual(report.replay_dry_runs(), [])
        self.assertEqual(report.rollback_dry_runs(), [])
        self.assertEqual(report.failed_recovery_dry_runs(), [])
        self.assertTrue(report.blocked_deferred_dry_runs())
        self.assertFalse(report.dry_run_summary()["would_execute_anything"])

    def test_guard_risk_simulation(self) -> None:
        report = self._executor().dry_run(self._approved_contract_report("dry-run-guard"))
        guard = report.guard_simulation()

        self.assertEqual(guard["status"], "simulated")
        self.assertTrue(guard["all_executable_false"])
        self.assertTrue(guard["all_guards_ok"])
        self.assertEqual(guard["simulated_action"], "simulate_guard_and_risk_checks")

    def test_dry_run_report_is_immutable(self) -> None:
        report = self._executor().dry_run(self._approved_contract_report("dry-run-immutable"))

        payload = report.payload
        payload["read_only"] = False
        report.rollback_dry_runs().append({"dry_run_id": "polluted"})

        self.assertTrue(report.payload["read_only"])
        self.assertNotIn(
            "polluted",
            [item.get("dry_run_id") for item in report.rollback_dry_runs()],
        )


if __name__ == "__main__":
    unittest.main()
