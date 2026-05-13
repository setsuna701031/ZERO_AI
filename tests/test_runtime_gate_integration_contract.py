from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeGateIntegrationContractTest(unittest.TestCase):
    def _policy_gate(self, effect, target="lifecycle", action="queue"):
        from core.runtime.runtime_execution_gate import RuntimeExecutionGate
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine, RuntimePolicyRule

        policy_engine = RuntimePolicyEngine()
        policy_engine.add_rule(
            RuntimePolicyRule(
                rule_id=f"{effect}-1",
                target=target,
                action=action,
                effect=effect,
                risk_level="high",
                reason=f"{effect} by contract",
            )
        )
        return RuntimeExecutionGate(policy_engine=policy_engine)

    def _manager_with_completed_session(self):
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager

        manager = RuntimeExecutionSessionManager()
        manager.create_session("session-1", "life-session-1")
        manager.start_session("session-1")
        manager.complete_session("session-1")
        return manager

    def _manager_with_failed_source(self):
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager

        manager = RuntimeExecutionSessionManager()
        manager.create_session("source-1", "life-source-1")
        manager.start_session("source-1")
        manager.fail_session("source-1")
        return manager

    def test_gated_lifecycle_queue_allowed(self) -> None:
        from core.runtime.runtime_gate_integration import RuntimeGateIntegration

        result = RuntimeGateIntegration().gated_lifecycle_queue("life-1")

        self.assertEqual(result.operation, "gated_lifecycle_queue")
        self.assertEqual(result.runtime_result.phase, "queued")

    def test_gated_lifecycle_dispatch_allowed(self) -> None:
        from core.runtime.runtime_gate_integration import RuntimeGateIntegration

        integration = RuntimeGateIntegration()
        integration.gated_lifecycle_queue("life-1")
        result = integration.gated_lifecycle_dispatch("life-1")

        self.assertEqual(result.runtime_result.phase, "dispatched")

    def test_gated_lifecycle_start_execution_allowed(self) -> None:
        from core.runtime.runtime_gate_integration import RuntimeGateIntegration

        integration = RuntimeGateIntegration()
        integration.gated_lifecycle_queue("life-1")
        integration.gated_lifecycle_dispatch("life-1")
        result = integration.gated_lifecycle_start_execution("life-1")

        self.assertEqual(result.runtime_result.phase, "executing")

    def test_gated_lifecycle_complete_execution_allowed(self) -> None:
        from core.runtime.runtime_gate_integration import RuntimeGateIntegration

        integration = RuntimeGateIntegration()
        integration.gated_lifecycle_queue("life-1")
        integration.gated_lifecycle_dispatch("life-1")
        integration.gated_lifecycle_start_execution("life-1")
        result = integration.gated_lifecycle_complete_execution("life-1")

        self.assertEqual(result.runtime_result.phase, "completed")

    def test_gated_lifecycle_fail_execution_allowed(self) -> None:
        from core.runtime.runtime_gate_integration import RuntimeGateIntegration

        integration = RuntimeGateIntegration()
        integration.gated_lifecycle_queue("life-1")
        integration.gated_lifecycle_dispatch("life-1")
        integration.gated_lifecycle_start_execution("life-1")
        result = integration.gated_lifecycle_fail_execution("life-1")

        self.assertEqual(result.runtime_result.phase, "failed")

    def test_gate_deny_blocks_lifecycle_operation(self) -> None:
        from core.runtime.runtime_gate_integration import (
            RuntimeGateIntegration,
            RuntimeGateIntegrationRejected,
        )
        from core.runtime.runtime_lifecycle_pipeline import RuntimeLifecyclePipeline

        pipeline = RuntimeLifecyclePipeline()
        integration = RuntimeGateIntegration(
            gate=self._policy_gate("deny"),
            lifecycle_pipeline=pipeline,
        )

        with self.assertRaises(RuntimeGateIntegrationRejected):
            integration.gated_lifecycle_queue("life-1")

        self.assertEqual(pipeline.get_records(), [])

    def test_gate_require_confirmation_blocks_lifecycle_operation(self) -> None:
        from core.runtime.runtime_gate_integration import (
            RuntimeGateIntegration,
            RuntimeGateIntegrationRejected,
        )
        from core.runtime.runtime_lifecycle_pipeline import RuntimeLifecyclePipeline

        pipeline = RuntimeLifecyclePipeline()
        integration = RuntimeGateIntegration(
            gate=self._policy_gate("require_confirmation"),
            lifecycle_pipeline=pipeline,
        )

        with self.assertRaises(RuntimeGateIntegrationRejected):
            integration.gated_lifecycle_queue("life-1")

        self.assertEqual(pipeline.get_records(), [])

    def test_gated_replay_session_allowed(self) -> None:
        from core.runtime.runtime_gate_integration import RuntimeGateIntegration
        from core.runtime.runtime_replay_engine import RuntimeReplayEngine

        replay_engine = RuntimeReplayEngine(
            session_manager=self._manager_with_completed_session()
        )
        result = RuntimeGateIntegration(
            replay_engine=replay_engine
        ).gated_replay_session("replay-1", "session-1")

        self.assertEqual(result.runtime_result.replay_id, "replay-1")
        self.assertTrue(result.runtime_result.verified)

    def test_gated_create_recovery_allowed(self) -> None:
        from core.runtime.runtime_gate_integration import RuntimeGateIntegration
        from core.runtime.runtime_recovery_coordinator import RuntimeRecoveryCoordinator

        coordinator = RuntimeRecoveryCoordinator(
            session_manager=self._manager_with_failed_source()
        )
        result = RuntimeGateIntegration(
            recovery_coordinator=coordinator
        ).gated_create_recovery("recovery-1", "source-1")

        self.assertEqual(result.runtime_result.recovery_id, "recovery-1")
        self.assertEqual(result.runtime_result.status, "created")

    def test_gated_run_recovery_allowed(self) -> None:
        from core.runtime.runtime_gate_integration import RuntimeGateIntegration
        from core.runtime.runtime_recovery_coordinator import RuntimeRecoveryCoordinator

        coordinator = RuntimeRecoveryCoordinator(
            session_manager=self._manager_with_failed_source()
        )
        integration = RuntimeGateIntegration(recovery_coordinator=coordinator)
        integration.gated_create_recovery("recovery-1", "source-1")
        result = integration.gated_run_recovery("recovery-1")

        self.assertEqual(result.runtime_result.status, "replayed")

    def test_gated_verify_recovery_allowed(self) -> None:
        from core.runtime.runtime_gate_integration import RuntimeGateIntegration
        from core.runtime.runtime_recovery_coordinator import RuntimeRecoveryCoordinator

        coordinator = RuntimeRecoveryCoordinator(
            session_manager=self._manager_with_failed_source()
        )
        integration = RuntimeGateIntegration(recovery_coordinator=coordinator)
        integration.gated_create_recovery("recovery-1", "source-1")
        integration.gated_run_recovery("recovery-1")
        result = integration.gated_verify_recovery("recovery-1")

        self.assertTrue(result.runtime_result.verified)
        self.assertEqual(result.runtime_result.status, "verified")

    def test_runtime_exception_wraps_runtime_gate_integration_rejected(self) -> None:
        from core.runtime.runtime_gate_integration import (
            RuntimeGateIntegration,
            RuntimeGateIntegrationRejected,
        )

        integration = RuntimeGateIntegration()

        with self.assertRaises(RuntimeGateIntegrationRejected) as context:
            integration.gated_lifecycle_dispatch("life-1")

        self.assertIsNotNone(context.exception.gate_result)
        self.assertIsNotNone(context.exception.original_exception)

    def test_gate_exception_wraps_runtime_gate_integration_rejected(self) -> None:
        from core.runtime.runtime_gate_integration import (
            RuntimeGateIntegration,
            RuntimeGateIntegrationRejected,
        )

        original = ValueError("boom")

        class FailingGate:
            def assert_open(self, *_args, **_kwargs):
                raise original

        with self.assertRaises(RuntimeGateIntegrationRejected) as context:
            RuntimeGateIntegration(gate=FailingGate()).gated_lifecycle_queue("life-1")

        self.assertIs(context.exception.original_exception, original)

    def test_result_includes_gate_result(self) -> None:
        from core.runtime.runtime_gate_integration import RuntimeGateIntegration

        result = RuntimeGateIntegration().gated_lifecycle_queue("life-1")

        self.assertIsNotNone(result.gate_result)
        self.assertTrue(result.gate_result.allowed)

    def test_result_includes_runtime_result(self) -> None:
        from core.runtime.runtime_gate_integration import RuntimeGateIntegration

        result = RuntimeGateIntegration().gated_lifecycle_queue("life-1")

        self.assertIsNotNone(result.runtime_result)
        self.assertEqual(result.runtime_result.phase, "queued")

    def test_sequence_increments_globally(self) -> None:
        from core.runtime.runtime_gate_integration import RuntimeGateIntegration

        integration = RuntimeGateIntegration()
        first = integration.gated_lifecycle_queue("life-1")
        second = integration.gated_lifecycle_dispatch("life-1")

        self.assertEqual([first.sequence, second.sequence], [1, 2])

    def test_get_results_returns_copy(self) -> None:
        from core.runtime.runtime_gate_integration import RuntimeGateIntegration

        integration = RuntimeGateIntegration()
        integration.gated_lifecycle_queue("life-1")
        results = integration.get_results()
        results.clear()

        self.assertEqual(len(integration.get_results()), 1)

    def test_payload_preserved(self) -> None:
        from core.runtime.runtime_gate_integration import RuntimeGateIntegration

        payload = {"task_id": "task-1"}

        result = RuntimeGateIntegration().gated_lifecycle_queue(
            "life-1",
            payload=payload,
        )

        self.assertIs(result.payload, payload)
        self.assertIs(result.gate_result.payload, payload)
        self.assertIs(result.runtime_result.payload, payload)

    def test_metadata_preserved(self) -> None:
        from core.runtime.runtime_gate_integration import RuntimeGateIntegration

        metadata = {"source": "contract", "attempt": 1}

        result = RuntimeGateIntegration().gated_lifecycle_queue(
            "life-1",
            metadata=metadata,
        )

        self.assertIs(result.metadata, metadata)
        self.assertIs(result.gate_result.metadata, metadata)
        self.assertIs(result.runtime_result.metadata, metadata)

    def test_payload_not_mutated(self) -> None:
        from core.runtime.runtime_gate_integration import RuntimeGateIntegration

        payload = {"items": [{"task_id": "task-1"}]}
        before = copy.deepcopy(payload)

        RuntimeGateIntegration().gated_lifecycle_queue("life-1", payload=payload)

        self.assertEqual(payload, before)

    def test_metadata_not_mutated(self) -> None:
        from core.runtime.runtime_gate_integration import RuntimeGateIntegration

        metadata = {"tags": ["contract"], "attempt": 1}
        before = copy.deepcopy(metadata)

        RuntimeGateIntegration().gated_lifecycle_queue("life-1", metadata=metadata)

        self.assertEqual(metadata, before)

    def test_clear_resets_integration_and_sequence(self) -> None:
        from core.runtime.runtime_gate_integration import RuntimeGateIntegration

        integration = RuntimeGateIntegration()
        integration.gated_lifecycle_queue("life-1")
        integration.clear()
        result = integration.gated_lifecycle_queue("life-2")

        self.assertEqual(result.sequence, 1)
        self.assertEqual(len(integration.get_results()), 1)


if __name__ == "__main__":
    unittest.main()
