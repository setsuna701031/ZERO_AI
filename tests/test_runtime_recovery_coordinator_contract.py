from __future__ import annotations

import copy
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeRecoveryCoordinatorContractTest(unittest.TestCase):
    def _manager_with_failed_source(self):
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager

        manager = RuntimeExecutionSessionManager()
        manager.create_session("source-1", "life-source-1")
        manager.start_session("source-1")
        manager.fail_session("source-1")
        return manager

    def _coordinator_with_failed_source(self):
        from core.runtime.runtime_recovery_coordinator import RuntimeRecoveryCoordinator

        return RuntimeRecoveryCoordinator(
            session_manager=self._manager_with_failed_source()
        )

    def test_empty_recovery_id_rejected(self) -> None:
        from core.runtime.runtime_recovery_coordinator import (
            RuntimeRecoveryCoordinator,
            RuntimeRecoveryRejected,
        )

        with self.assertRaises(RuntimeRecoveryRejected):
            RuntimeRecoveryCoordinator().create_recovery("", "source-1")

    def test_duplicate_recovery_id_rejected(self) -> None:
        from core.runtime.runtime_recovery_coordinator import RuntimeRecoveryRejected

        coordinator = self._coordinator_with_failed_source()
        coordinator.create_recovery("recovery-1", "source-1")

        with self.assertRaises(RuntimeRecoveryRejected):
            coordinator.create_recovery("recovery-1", "source-1")

    def test_missing_source_session_rejected(self) -> None:
        from core.runtime.runtime_recovery_coordinator import RuntimeRecoveryRejected

        with self.assertRaises(RuntimeRecoveryRejected):
            self._coordinator_with_failed_source().create_recovery(
                "recovery-1",
                "missing",
            )

    def test_source_session_must_be_failed(self) -> None:
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager
        from core.runtime.runtime_recovery_coordinator import (
            RuntimeRecoveryCoordinator,
            RuntimeRecoveryRejected,
        )

        manager = RuntimeExecutionSessionManager()
        manager.create_session("source-1", "life-source-1")
        manager.start_session("source-1")
        manager.complete_session("source-1")

        with self.assertRaises(RuntimeRecoveryRejected):
            RuntimeRecoveryCoordinator(session_manager=manager).create_recovery(
                "recovery-1",
                "source-1",
            )

    def test_create_recovery_creates_plan(self) -> None:
        plan = self._coordinator_with_failed_source().create_recovery(
            "recovery-1",
            "source-1",
        )

        self.assertEqual(plan.recovery_id, "recovery-1")
        self.assertEqual(plan.source_session_id, "source-1")
        self.assertEqual(plan.status, "created")
        self.assertFalse(plan.verified)

    def test_create_recovery_auto_generates_repair_session_id(self) -> None:
        plan = self._coordinator_with_failed_source().create_recovery(
            "recovery-1",
            "source-1",
        )

        self.assertEqual(plan.repair_session_id, "recovery-1:repair")

    def test_create_recovery_auto_generates_replay_id(self) -> None:
        plan = self._coordinator_with_failed_source().create_recovery(
            "recovery-1",
            "source-1",
        )

        self.assertEqual(plan.replay_id, "recovery-1:replay")

    def test_repair_session_parent_points_to_source_session(self) -> None:
        coordinator = self._coordinator_with_failed_source()
        plan = coordinator.create_recovery("recovery-1", "source-1")

        repair_session = coordinator.session_manager.get_session(
            plan.repair_session_id
        )

        self.assertEqual(repair_session.parent_session_id, "source-1")

    def test_recovery_steps_created_in_stable_order(self) -> None:
        plan = self._coordinator_with_failed_source().create_recovery(
            "recovery-1",
            "source-1",
        )

        self.assertEqual(
            [step.step_type for step in plan.steps],
            [
                "detect_failure",
                "create_repair_session",
                "mark_incident",
                "mark_repaired",
                "prepare_replay",
            ],
        )

    def test_step_sequence_starts_at_1(self) -> None:
        plan = self._coordinator_with_failed_source().create_recovery(
            "recovery-1",
            "source-1",
        )

        self.assertEqual([step.sequence for step in plan.steps], [1, 2, 3, 4, 5])

    def test_recovery_plan_sequence_increments_globally(self) -> None:
        coordinator = self._coordinator_with_failed_source()
        first = coordinator.create_recovery("recovery-1", "source-1")
        second = coordinator.create_recovery("recovery-2", "source-1")

        self.assertEqual([first.sequence, second.sequence], [1, 2])

    def test_run_recovery_completes_all_steps_without_handler(self) -> None:
        coordinator = self._coordinator_with_failed_source()
        coordinator.create_recovery("recovery-1", "source-1")

        plan = coordinator.run_recovery("recovery-1")

        self.assertEqual(plan.status, "replayed")
        self.assertTrue(all(step.status == "completed" for step in plan.steps))

    def test_run_recovery_calls_handler_in_step_sequence_order(self) -> None:
        received = []
        coordinator = self._coordinator_with_failed_source()
        coordinator.create_recovery("recovery-1", "source-1")

        coordinator.run_recovery(
            "recovery-1",
            handler=lambda step: received.append(step.sequence),
        )

        self.assertEqual(received, [1, 2, 3, 4, 5])

    def test_handler_result_stored_in_step_result(self) -> None:
        coordinator = self._coordinator_with_failed_source()
        coordinator.create_recovery("recovery-1", "source-1")

        plan = coordinator.run_recovery(
            "recovery-1",
            handler=lambda step: f"result:{step.step_type}",
        )

        self.assertEqual(
            [step.result for step in plan.steps],
            [f"result:{step.step_type}" for step in plan.steps],
        )

    def test_handler_exception_raises_runtime_recovery_rejected(self) -> None:
        from core.runtime.runtime_recovery_coordinator import RuntimeRecoveryRejected

        original = ValueError("boom")

        def fail(_step):
            raise original

        coordinator = self._coordinator_with_failed_source()
        coordinator.create_recovery("recovery-1", "source-1")

        with self.assertRaises(RuntimeRecoveryRejected) as context:
            coordinator.run_recovery("recovery-1", handler=fail)

        self.assertIs(context.exception.original_exception, original)

    def test_run_recovery_creates_replay_session(self) -> None:
        coordinator = self._coordinator_with_failed_source()
        plan = coordinator.create_recovery("recovery-1", "source-1")

        coordinator.run_recovery("recovery-1")

        self.assertIsNotNone(coordinator.replay_engine.get_replay(plan.replay_id))

    def test_verify_requires_replayed_status(self) -> None:
        from core.runtime.runtime_recovery_coordinator import RuntimeRecoveryRejected

        coordinator = self._coordinator_with_failed_source()
        coordinator.create_recovery("recovery-1", "source-1")

        with self.assertRaises(RuntimeRecoveryRejected):
            coordinator.verify_recovery("recovery-1")

    def test_verify_marks_plan_verified(self) -> None:
        coordinator = self._coordinator_with_failed_source()
        coordinator.create_recovery("recovery-1", "source-1")
        coordinator.run_recovery("recovery-1")

        plan = coordinator.verify_recovery("recovery-1")

        self.assertEqual(plan.status, "verified")
        self.assertTrue(plan.verified)

    def test_verify_requires_replay_verified_true(self) -> None:
        from core.runtime.runtime_recovery_coordinator import (
            RuntimeRecoveryCoordinator,
            RuntimeRecoveryRejected,
        )

        @dataclass(frozen=True)
        class UnverifiedReplay:
            verified: bool = False

        class UnverifiedReplayEngine:
            def __init__(self) -> None:
                self.replay = None

            def replay_session(self, *_args, **_kwargs):
                self.replay = UnverifiedReplay()
                return self.replay

            def get_replay(self, _replay_id):
                return self.replay

        coordinator = RuntimeRecoveryCoordinator(
            session_manager=self._manager_with_failed_source(),
            replay_engine=UnverifiedReplayEngine(),
        )
        coordinator.create_recovery("recovery-1", "source-1")
        coordinator.run_recovery("recovery-1")

        with self.assertRaises(RuntimeRecoveryRejected):
            coordinator.verify_recovery("recovery-1")

    def test_payload_preserved(self) -> None:
        payload = {"error": "failed", "items": [1, 2]}

        plan = self._coordinator_with_failed_source().create_recovery(
            "recovery-1",
            "source-1",
            payload=payload,
        )

        self.assertIs(plan.payload, payload)
        self.assertIs(plan.steps[0].payload, payload)

    def test_metadata_preserved(self) -> None:
        metadata = {"source": "contract", "attempt": 1}

        plan = self._coordinator_with_failed_source().create_recovery(
            "recovery-1",
            "source-1",
            metadata=metadata,
        )

        self.assertIs(plan.metadata, metadata)
        self.assertIs(plan.steps[0].metadata, metadata)

    def test_payload_not_mutated(self) -> None:
        payload = {"items": [{"phase": "failed"}]}
        before = copy.deepcopy(payload)

        self._coordinator_with_failed_source().create_recovery(
            "recovery-1",
            "source-1",
            payload=payload,
        )

        self.assertEqual(payload, before)

    def test_metadata_not_mutated(self) -> None:
        metadata = {"tags": ["contract"], "attempt": 1}
        before = copy.deepcopy(metadata)

        self._coordinator_with_failed_source().create_recovery(
            "recovery-1",
            "source-1",
            metadata=metadata,
        )

        self.assertEqual(metadata, before)

    def test_get_recovery_returns_copy(self) -> None:
        coordinator = self._coordinator_with_failed_source()
        coordinator.create_recovery("recovery-1", "source-1")
        plan = coordinator.get_recovery("recovery-1")
        plan.steps.clear()

        self.assertEqual(len(coordinator.get_recovery("recovery-1").steps), 5)

    def test_get_recoveries_returns_copy(self) -> None:
        coordinator = self._coordinator_with_failed_source()
        coordinator.create_recovery("recovery-1", "source-1")
        plans = coordinator.get_recoveries()
        plans[0].steps.clear()
        plans.clear()

        self.assertEqual(len(coordinator.get_recoveries()), 1)
        self.assertEqual(len(coordinator.get_recoveries()[0].steps), 5)

    def test_clear_resets_recovery_coordinator(self) -> None:
        coordinator = self._coordinator_with_failed_source()
        coordinator.create_recovery("recovery-1", "source-1")
        coordinator.clear()
        plan = coordinator.create_recovery("recovery-2", "source-1")

        self.assertEqual(plan.sequence, 1)
        self.assertEqual(
            [stored.recovery_id for stored in coordinator.get_recoveries()],
            ["recovery-2"],
        )

    def test_session_replay_exception_wraps_runtime_recovery_rejected(self) -> None:
        from core.runtime.runtime_recovery_coordinator import (
            RuntimeRecoveryCoordinator,
            RuntimeRecoveryRejected,
        )

        original = ValueError("boom")

        class FailingSessionManager:
            def get_session(self, _session_id):
                raise original

        with self.assertRaises(RuntimeRecoveryRejected) as context:
            RuntimeRecoveryCoordinator(
                session_manager=FailingSessionManager()
            ).create_recovery("recovery-1", "source-1")

        self.assertIs(context.exception.original_exception, original)

    def test_replay_exception_wraps_runtime_recovery_rejected(self) -> None:
        from core.runtime.runtime_recovery_coordinator import (
            RuntimeRecoveryCoordinator,
            RuntimeRecoveryRejected,
        )

        original = ValueError("boom")

        class FailingReplayEngine:
            def replay_session(self, *_args, **_kwargs):
                raise original

            def get_replay(self, _replay_id):
                return None

        coordinator = RuntimeRecoveryCoordinator(
            session_manager=self._manager_with_failed_source(),
            replay_engine=FailingReplayEngine(),
        )
        coordinator.create_recovery("recovery-1", "source-1")

        with self.assertRaises(RuntimeRecoveryRejected) as context:
            coordinator.run_recovery("recovery-1")

        self.assertIs(context.exception.original_exception, original)


if __name__ == "__main__":
    unittest.main()
