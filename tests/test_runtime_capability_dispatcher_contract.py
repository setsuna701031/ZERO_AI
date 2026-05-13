from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeCapabilityDispatcherContractTest(unittest.TestCase):
    def _dispatcher(self):
        from core.runtime.runtime_capability_dispatcher import RuntimeCapabilityDispatcher

        return RuntimeCapabilityDispatcher()

    def _dispatcher_with_completed_session(self):
        from core.runtime.runtime_capability_dispatcher import RuntimeCapabilityDispatcher
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager
        from core.runtime.runtime_gate_integration import RuntimeGateIntegration
        from core.runtime.runtime_intent_gate_router import RuntimeIntentGateRouter
        from core.runtime.runtime_replay_engine import RuntimeReplayEngine

        manager = RuntimeExecutionSessionManager()
        manager.create_session("session-1", "life-session-1")
        manager.start_session("session-1")
        manager.complete_session("session-1")
        router = RuntimeIntentGateRouter(
            gate_integration=RuntimeGateIntegration(
                replay_engine=RuntimeReplayEngine(session_manager=manager)
            )
        )
        return RuntimeCapabilityDispatcher(router=router)

    def _dispatcher_with_failed_source(self):
        from core.runtime.runtime_capability_dispatcher import RuntimeCapabilityDispatcher
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager
        from core.runtime.runtime_gate_integration import RuntimeGateIntegration
        from core.runtime.runtime_intent_gate_router import RuntimeIntentGateRouter
        from core.runtime.runtime_recovery_coordinator import RuntimeRecoveryCoordinator

        manager = RuntimeExecutionSessionManager()
        manager.create_session("source-1", "life-source-1")
        manager.start_session("source-1")
        manager.fail_session("source-1")
        router = RuntimeIntentGateRouter(
            gate_integration=RuntimeGateIntegration(
                recovery_coordinator=RuntimeRecoveryCoordinator(
                    session_manager=manager
                )
            )
        )
        return RuntimeCapabilityDispatcher(router=router)

    def test_dispatch_lifecycle_queue(self) -> None:
        result = self._dispatcher().dispatch(
            "lifecycle.queue",
            runtime_args={"lifecycle_id": "life-1"},
        )

        self.assertEqual(result.operation, "lifecycle.queue")
        self.assertEqual(result.route_result.runtime_result.phase, "queued")

    def test_dispatch_lifecycle_dispatch(self) -> None:
        dispatcher = self._dispatcher()
        dispatcher.dispatch("lifecycle.queue", runtime_args={"lifecycle_id": "life-1"})
        result = dispatcher.dispatch(
            "lifecycle.dispatch",
            runtime_args={"lifecycle_id": "life-1"},
        )

        self.assertEqual(result.route_result.runtime_result.phase, "dispatched")

    def test_dispatch_lifecycle_start_execution(self) -> None:
        dispatcher = self._dispatcher()
        dispatcher.dispatch("lifecycle.queue", runtime_args={"lifecycle_id": "life-1"})
        dispatcher.dispatch("lifecycle.dispatch", runtime_args={"lifecycle_id": "life-1"})
        result = dispatcher.dispatch(
            "lifecycle.start_execution",
            runtime_args={"lifecycle_id": "life-1"},
        )

        self.assertEqual(result.route_result.runtime_result.phase, "executing")

    def test_dispatch_lifecycle_complete_execution(self) -> None:
        dispatcher = self._dispatcher()
        dispatcher.dispatch("lifecycle.queue", runtime_args={"lifecycle_id": "life-1"})
        dispatcher.dispatch("lifecycle.dispatch", runtime_args={"lifecycle_id": "life-1"})
        dispatcher.dispatch(
            "lifecycle.start_execution",
            runtime_args={"lifecycle_id": "life-1"},
        )
        result = dispatcher.dispatch(
            "lifecycle.complete_execution",
            runtime_args={"lifecycle_id": "life-1"},
        )

        self.assertEqual(result.route_result.runtime_result.phase, "completed")

    def test_dispatch_lifecycle_fail_execution(self) -> None:
        dispatcher = self._dispatcher()
        dispatcher.dispatch("lifecycle.queue", runtime_args={"lifecycle_id": "life-1"})
        dispatcher.dispatch("lifecycle.dispatch", runtime_args={"lifecycle_id": "life-1"})
        dispatcher.dispatch(
            "lifecycle.start_execution",
            runtime_args={"lifecycle_id": "life-1"},
        )
        result = dispatcher.dispatch(
            "lifecycle.fail_execution",
            runtime_args={"lifecycle_id": "life-1"},
        )

        self.assertEqual(result.route_result.runtime_result.phase, "failed")

    def test_dispatch_replay_session(self) -> None:
        result = self._dispatcher_with_completed_session().dispatch(
            "replay.session",
            runtime_args={
                "replay_id": "replay-1",
                "source_session_id": "session-1",
            },
        )

        self.assertEqual(result.route_result.runtime_result.replay_id, "replay-1")
        self.assertTrue(result.route_result.runtime_result.verified)

    def test_dispatch_recovery_create(self) -> None:
        result = self._dispatcher_with_failed_source().dispatch(
            "recovery.create",
            runtime_args={
                "recovery_id": "recovery-1",
                "source_session_id": "source-1",
            },
        )

        self.assertEqual(result.route_result.runtime_result.status, "created")

    def test_dispatch_recovery_run(self) -> None:
        dispatcher = self._dispatcher_with_failed_source()
        dispatcher.dispatch(
            "recovery.create",
            runtime_args={
                "recovery_id": "recovery-1",
                "source_session_id": "source-1",
            },
        )
        result = dispatcher.dispatch(
            "recovery.run",
            runtime_args={"recovery_id": "recovery-1"},
        )

        self.assertEqual(result.route_result.runtime_result.status, "replayed")

    def test_dispatch_recovery_verify(self) -> None:
        dispatcher = self._dispatcher_with_failed_source()
        dispatcher.dispatch(
            "recovery.create",
            runtime_args={
                "recovery_id": "recovery-1",
                "source_session_id": "source-1",
            },
        )
        dispatcher.dispatch("recovery.run", runtime_args={"recovery_id": "recovery-1"})
        result = dispatcher.dispatch(
            "recovery.verify",
            runtime_args={"recovery_id": "recovery-1"},
        )

        self.assertTrue(result.route_result.runtime_result.verified)
        self.assertEqual(result.route_result.runtime_result.status, "verified")

    def test_empty_operation_rejected(self) -> None:
        from core.runtime.runtime_capability_dispatcher import (
            RuntimeCapabilityDispatchRejected,
        )

        with self.assertRaises(RuntimeCapabilityDispatchRejected):
            self._dispatcher().dispatch("", runtime_args={"lifecycle_id": "life-1"})

    def test_unknown_operation_rejected(self) -> None:
        from core.runtime.runtime_capability_dispatcher import (
            RuntimeCapabilityDispatchRejected,
        )

        with self.assertRaises(RuntimeCapabilityDispatchRejected) as context:
            self._dispatcher().dispatch(
                "unknown.operation",
                runtime_args={"lifecycle_id": "life-1"},
            )

        self.assertIsNotNone(context.exception.original_exception)

    def test_resolver_rejection_wraps_runtime_capability_dispatch_rejected(self) -> None:
        from core.runtime.runtime_capability_dispatcher import (
            RuntimeCapabilityDispatcher,
            RuntimeCapabilityDispatchRejected,
        )
        from core.runtime.runtime_capability_resolver import RuntimeCapabilityRejected

        original = RuntimeCapabilityRejected("boom")

        class FailingResolver:
            def resolve(self, _operation):
                raise original

        with self.assertRaises(RuntimeCapabilityDispatchRejected) as context:
            RuntimeCapabilityDispatcher(resolver=FailingResolver()).dispatch(
                "lifecycle.queue",
                runtime_args={"lifecycle_id": "life-1"},
            )

        self.assertIs(context.exception.original_exception, original)

    def test_router_rejection_wraps_runtime_capability_dispatch_rejected(self) -> None:
        from core.runtime.runtime_capability_dispatcher import (
            RuntimeCapabilityDispatchRejected,
        )

        with self.assertRaises(RuntimeCapabilityDispatchRejected) as context:
            self._dispatcher().dispatch(
                "lifecycle.dispatch",
                runtime_args={"lifecycle_id": "life-1"},
            )

        self.assertIsNotNone(context.exception.original_exception)

    def test_result_includes_capability(self) -> None:
        result = self._dispatcher().dispatch(
            "lifecycle.queue",
            runtime_args={"lifecycle_id": "life-1"},
        )

        self.assertEqual(result.capability.operation, "lifecycle.queue")
        self.assertEqual(result.capability.target, "lifecycle")

    def test_result_includes_route_result(self) -> None:
        result = self._dispatcher().dispatch(
            "lifecycle.queue",
            runtime_args={"lifecycle_id": "life-1"},
        )

        self.assertEqual(result.route_result.operation, "lifecycle.queue")
        self.assertEqual(result.route_result.runtime_result.phase, "queued")

    def test_sequence_increments_globally(self) -> None:
        dispatcher = self._dispatcher()
        first = dispatcher.dispatch(
            "lifecycle.queue",
            runtime_args={"lifecycle_id": "life-1"},
        )
        second = dispatcher.dispatch(
            "lifecycle.dispatch",
            runtime_args={"lifecycle_id": "life-1"},
        )

        self.assertEqual([first.sequence, second.sequence], [1, 2])

    def test_dispatch_many_preserves_input_order(self) -> None:
        dispatcher = self._dispatcher()
        results = dispatcher.dispatch_many(
            [
                {
                    "operation": "lifecycle.queue",
                    "runtime_args": {"lifecycle_id": "life-1"},
                },
                {
                    "operation": "lifecycle.dispatch",
                    "runtime_args": {"lifecycle_id": "life-1"},
                },
            ]
        )

        self.assertEqual(
            [result.operation for result in results],
            ["lifecycle.queue", "lifecycle.dispatch"],
        )

    def test_dispatch_many_rejects_if_any_request_invalid(self) -> None:
        from core.runtime.runtime_capability_dispatcher import (
            RuntimeCapabilityDispatchRejected,
        )

        with self.assertRaises(RuntimeCapabilityDispatchRejected) as context:
            self._dispatcher().dispatch_many(
                [
                    {
                        "operation": "lifecycle.queue",
                        "runtime_args": {"lifecycle_id": "life-1"},
                    },
                    {
                        "operation": "unknown.operation",
                        "runtime_args": {"lifecycle_id": "life-1"},
                    },
                ]
            )

        self.assertIsNotNone(context.exception.original_exception)

    def test_get_results_returns_copy(self) -> None:
        dispatcher = self._dispatcher()
        dispatcher.dispatch("lifecycle.queue", runtime_args={"lifecycle_id": "life-1"})
        results = dispatcher.get_results()
        results.clear()

        self.assertEqual(len(dispatcher.get_results()), 1)

    def test_payload_preserved(self) -> None:
        payload = {"task_id": "task-1"}

        result = self._dispatcher().dispatch(
            "lifecycle.queue",
            runtime_args={"lifecycle_id": "life-1"},
            payload=payload,
        )

        self.assertIs(result.payload, payload)
        self.assertIs(result.route_result.payload, payload)

    def test_metadata_preserved(self) -> None:
        metadata = {"source": "contract", "attempt": 1}

        result = self._dispatcher().dispatch(
            "lifecycle.queue",
            runtime_args={"lifecycle_id": "life-1"},
            metadata=metadata,
        )

        self.assertIs(result.metadata, metadata)
        self.assertIs(result.route_result.metadata, metadata)

    def test_runtime_args_preserved(self) -> None:
        runtime_args = {"lifecycle_id": "life-1"}

        result = self._dispatcher().dispatch(
            "lifecycle.queue",
            runtime_args=runtime_args,
        )

        self.assertIs(result.runtime_args, runtime_args)

    def test_payload_not_mutated(self) -> None:
        payload = {"items": [{"task_id": "task-1"}]}
        before = copy.deepcopy(payload)

        self._dispatcher().dispatch(
            "lifecycle.queue",
            runtime_args={"lifecycle_id": "life-1"},
            payload=payload,
        )

        self.assertEqual(payload, before)

    def test_metadata_not_mutated(self) -> None:
        metadata = {"tags": ["contract"], "attempt": 1}
        before = copy.deepcopy(metadata)

        self._dispatcher().dispatch(
            "lifecycle.queue",
            runtime_args={"lifecycle_id": "life-1"},
            metadata=metadata,
        )

        self.assertEqual(metadata, before)

    def test_runtime_args_not_mutated(self) -> None:
        runtime_args = {"lifecycle_id": "life-1", "tags": ["contract"]}
        before = copy.deepcopy(runtime_args)

        self._dispatcher().dispatch("lifecycle.queue", runtime_args=runtime_args)

        self.assertEqual(runtime_args, before)

    def test_clear_resets_dispatcher_and_sequence(self) -> None:
        dispatcher = self._dispatcher()
        dispatcher.dispatch("lifecycle.queue", runtime_args={"lifecycle_id": "life-1"})
        dispatcher.clear()
        result = dispatcher.dispatch(
            "lifecycle.queue",
            runtime_args={"lifecycle_id": "life-2"},
        )

        self.assertEqual(result.sequence, 1)
        self.assertEqual(len(dispatcher.get_results()), 1)


if __name__ == "__main__":
    unittest.main()
