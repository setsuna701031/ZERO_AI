from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeIntentGateRouterContractTest(unittest.TestCase):
    def _router(self):
        from core.runtime.runtime_intent_gate_router import RuntimeIntentGateRouter

        return RuntimeIntentGateRouter()

    def _router_with_completed_session(self):
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager
        from core.runtime.runtime_gate_integration import RuntimeGateIntegration
        from core.runtime.runtime_intent_gate_router import RuntimeIntentGateRouter
        from core.runtime.runtime_replay_engine import RuntimeReplayEngine

        manager = RuntimeExecutionSessionManager()
        manager.create_session("session-1", "life-session-1")
        manager.start_session("session-1")
        manager.complete_session("session-1")
        return RuntimeIntentGateRouter(
            gate_integration=RuntimeGateIntegration(
                replay_engine=RuntimeReplayEngine(session_manager=manager)
            )
        )

    def _router_with_failed_source(self):
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager
        from core.runtime.runtime_gate_integration import RuntimeGateIntegration
        from core.runtime.runtime_intent_gate_router import RuntimeIntentGateRouter
        from core.runtime.runtime_recovery_coordinator import RuntimeRecoveryCoordinator

        manager = RuntimeExecutionSessionManager()
        manager.create_session("source-1", "life-source-1")
        manager.start_session("source-1")
        manager.fail_session("source-1")
        return RuntimeIntentGateRouter(
            gate_integration=RuntimeGateIntegration(
                recovery_coordinator=RuntimeRecoveryCoordinator(
                    session_manager=manager
                )
            )
        )

    def test_route_lifecycle_queue(self) -> None:
        result = self._router().route(
            "lifecycle.queue",
            runtime_args={"lifecycle_id": "life-1"},
        )

        self.assertEqual(result.operation, "lifecycle.queue")
        self.assertEqual(result.runtime_result.phase, "queued")

    def test_route_lifecycle_dispatch(self) -> None:
        router = self._router()
        router.route("lifecycle.queue", runtime_args={"lifecycle_id": "life-1"})
        result = router.route(
            "lifecycle.dispatch",
            runtime_args={"lifecycle_id": "life-1"},
        )

        self.assertEqual(result.runtime_result.phase, "dispatched")

    def test_route_lifecycle_start_execution(self) -> None:
        router = self._router()
        router.route("lifecycle.queue", runtime_args={"lifecycle_id": "life-1"})
        router.route("lifecycle.dispatch", runtime_args={"lifecycle_id": "life-1"})
        result = router.route(
            "lifecycle.start_execution",
            runtime_args={"lifecycle_id": "life-1"},
        )

        self.assertEqual(result.runtime_result.phase, "executing")

    def test_route_lifecycle_complete_execution(self) -> None:
        router = self._router()
        router.route("lifecycle.queue", runtime_args={"lifecycle_id": "life-1"})
        router.route("lifecycle.dispatch", runtime_args={"lifecycle_id": "life-1"})
        router.route(
            "lifecycle.start_execution",
            runtime_args={"lifecycle_id": "life-1"},
        )
        result = router.route(
            "lifecycle.complete_execution",
            runtime_args={"lifecycle_id": "life-1"},
        )

        self.assertEqual(result.runtime_result.phase, "completed")

    def test_route_lifecycle_fail_execution(self) -> None:
        router = self._router()
        router.route("lifecycle.queue", runtime_args={"lifecycle_id": "life-1"})
        router.route("lifecycle.dispatch", runtime_args={"lifecycle_id": "life-1"})
        router.route(
            "lifecycle.start_execution",
            runtime_args={"lifecycle_id": "life-1"},
        )
        result = router.route(
            "lifecycle.fail_execution",
            runtime_args={"lifecycle_id": "life-1"},
        )

        self.assertEqual(result.runtime_result.phase, "failed")

    def test_route_replay_session(self) -> None:
        result = self._router_with_completed_session().route(
            "replay.session",
            runtime_args={
                "replay_id": "replay-1",
                "source_session_id": "session-1",
            },
        )

        self.assertEqual(result.runtime_result.replay_id, "replay-1")
        self.assertTrue(result.runtime_result.verified)

    def test_route_recovery_create(self) -> None:
        result = self._router_with_failed_source().route(
            "recovery.create",
            runtime_args={
                "recovery_id": "recovery-1",
                "source_session_id": "source-1",
            },
        )

        self.assertEqual(result.runtime_result.status, "created")

    def test_route_recovery_run(self) -> None:
        router = self._router_with_failed_source()
        router.route(
            "recovery.create",
            runtime_args={
                "recovery_id": "recovery-1",
                "source_session_id": "source-1",
            },
        )
        result = router.route(
            "recovery.run",
            runtime_args={"recovery_id": "recovery-1"},
        )

        self.assertEqual(result.runtime_result.status, "replayed")

    def test_route_recovery_verify(self) -> None:
        router = self._router_with_failed_source()
        router.route(
            "recovery.create",
            runtime_args={
                "recovery_id": "recovery-1",
                "source_session_id": "source-1",
            },
        )
        router.route("recovery.run", runtime_args={"recovery_id": "recovery-1"})
        result = router.route(
            "recovery.verify",
            runtime_args={"recovery_id": "recovery-1"},
        )

        self.assertTrue(result.runtime_result.verified)
        self.assertEqual(result.runtime_result.status, "verified")

    def test_unknown_operation_rejected(self) -> None:
        from core.runtime.runtime_intent_gate_router import RuntimeIntentRouteRejected

        with self.assertRaises(RuntimeIntentRouteRejected) as context:
            self._router().route(
                "unknown.operation",
                runtime_args={"lifecycle_id": "life-1"},
            )

        self.assertIsNotNone(context.exception.original_exception)

    def test_missing_lifecycle_id_rejected(self) -> None:
        from core.runtime.runtime_intent_gate_router import RuntimeIntentRouteRejected

        with self.assertRaises(RuntimeIntentRouteRejected):
            self._router().route("lifecycle.queue", runtime_args={})

    def test_missing_replay_args_rejected(self) -> None:
        from core.runtime.runtime_intent_gate_router import RuntimeIntentRouteRejected

        router = self._router()
        with self.assertRaises(RuntimeIntentRouteRejected):
            router.route("replay.session", runtime_args={"replay_id": "replay-1"})
        with self.assertRaises(RuntimeIntentRouteRejected):
            router.route(
                "replay.session",
                runtime_args={"source_session_id": "session-1"},
            )

    def test_missing_recovery_args_rejected(self) -> None:
        from core.runtime.runtime_intent_gate_router import RuntimeIntentRouteRejected

        router = self._router()
        with self.assertRaises(RuntimeIntentRouteRejected):
            router.route("recovery.create", runtime_args={"recovery_id": "recovery-1"})
        with self.assertRaises(RuntimeIntentRouteRejected):
            router.route("recovery.run", runtime_args={})
        with self.assertRaises(RuntimeIntentRouteRejected):
            router.route("recovery.verify", runtime_args={})

    def test_gate_integration_rejection_wraps_runtime_intent_route_rejected(self) -> None:
        from core.runtime.runtime_intent_gate_router import RuntimeIntentRouteRejected

        with self.assertRaises(RuntimeIntentRouteRejected) as context:
            self._router().route(
                "lifecycle.dispatch",
                runtime_args={"lifecycle_id": "life-1"},
            )

        self.assertIsNotNone(context.exception.original_exception)

    def test_classifier_rejection_wraps_runtime_intent_route_rejected(self) -> None:
        from core.runtime.runtime_intent_classifier import RuntimeIntentRejected
        from core.runtime.runtime_intent_gate_router import (
            RuntimeIntentGateRouter,
            RuntimeIntentRouteRejected,
        )

        original = RuntimeIntentRejected("boom")

        class FailingClassifier:
            def classify(self, *_args, **_kwargs):
                raise original

        with self.assertRaises(RuntimeIntentRouteRejected) as context:
            RuntimeIntentGateRouter(classifier=FailingClassifier()).route(
                "lifecycle.queue",
                runtime_args={"lifecycle_id": "life-1"},
            )

        self.assertIs(context.exception.original_exception, original)

    def test_result_includes_intent(self) -> None:
        result = self._router().route(
            "lifecycle.queue",
            runtime_args={"lifecycle_id": "life-1"},
        )

        self.assertEqual(result.intent.operation, "lifecycle.queue")
        self.assertEqual(result.intent.target, "lifecycle")

    def test_result_includes_gate_result(self) -> None:
        result = self._router().route(
            "lifecycle.queue",
            runtime_args={"lifecycle_id": "life-1"},
        )

        self.assertIsNotNone(result.gate_result)
        self.assertTrue(result.gate_result.allowed)

    def test_result_includes_runtime_result(self) -> None:
        result = self._router().route(
            "lifecycle.queue",
            runtime_args={"lifecycle_id": "life-1"},
        )

        self.assertIsNotNone(result.runtime_result)
        self.assertEqual(result.runtime_result.phase, "queued")

    def test_sequence_increments_globally(self) -> None:
        router = self._router()
        first = router.route("lifecycle.queue", runtime_args={"lifecycle_id": "life-1"})
        second = router.route(
            "lifecycle.dispatch",
            runtime_args={"lifecycle_id": "life-1"},
        )

        self.assertEqual([first.sequence, second.sequence], [1, 2])

    def test_get_results_returns_copy(self) -> None:
        router = self._router()
        router.route("lifecycle.queue", runtime_args={"lifecycle_id": "life-1"})
        results = router.get_results()
        results.clear()

        self.assertEqual(len(router.get_results()), 1)

    def test_payload_preserved(self) -> None:
        payload = {"task_id": "task-1"}

        result = self._router().route(
            "lifecycle.queue",
            runtime_args={"lifecycle_id": "life-1"},
            payload=payload,
        )

        self.assertIs(result.payload, payload)
        self.assertIs(result.intent.payload, payload)
        self.assertIs(result.gate_result.payload, payload)
        self.assertIs(result.runtime_result.payload, payload)

    def test_metadata_preserved(self) -> None:
        metadata = {"source": "contract", "attempt": 1}

        result = self._router().route(
            "lifecycle.queue",
            runtime_args={"lifecycle_id": "life-1"},
            metadata=metadata,
        )

        self.assertIs(result.metadata, metadata)
        self.assertIs(result.intent.metadata, metadata)
        self.assertIs(result.gate_result.metadata, metadata)
        self.assertIs(result.runtime_result.metadata, metadata)

    def test_runtime_args_not_mutated(self) -> None:
        runtime_args = {"lifecycle_id": "life-1", "tags": ["contract"]}
        before = copy.deepcopy(runtime_args)

        self._router().route("lifecycle.queue", runtime_args=runtime_args)

        self.assertEqual(runtime_args, before)

    def test_payload_not_mutated(self) -> None:
        payload = {"items": [{"task_id": "task-1"}]}
        before = copy.deepcopy(payload)

        self._router().route(
            "lifecycle.queue",
            runtime_args={"lifecycle_id": "life-1"},
            payload=payload,
        )

        self.assertEqual(payload, before)

    def test_metadata_not_mutated(self) -> None:
        metadata = {"tags": ["contract"], "attempt": 1}
        before = copy.deepcopy(metadata)

        self._router().route(
            "lifecycle.queue",
            runtime_args={"lifecycle_id": "life-1"},
            metadata=metadata,
        )

        self.assertEqual(metadata, before)

    def test_clear_resets_router_and_sequence(self) -> None:
        router = self._router()
        router.route("lifecycle.queue", runtime_args={"lifecycle_id": "life-1"})
        router.clear()
        result = router.route(
            "lifecycle.queue",
            runtime_args={"lifecycle_id": "life-2"},
        )

        self.assertEqual(result.sequence, 1)
        self.assertEqual(len(router.get_results()), 1)


if __name__ == "__main__":
    unittest.main()
