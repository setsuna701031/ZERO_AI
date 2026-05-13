from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeMutationGuardContractTest(unittest.TestCase):
    def test_scheduler_queue_transition_allowed(self) -> None:
        from core.runtime.runtime_mutation_guard import guard_mutation
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource

        request = guard_mutation(
            RuntimeOwner.SCHEDULER,
            RuntimeResource.QUEUE_STATE,
            RuntimeAction.TRANSITION,
        )

        self.assertTrue(request.allowed)
        self.assertIsNone(request.rejected_reason)

    def test_scheduler_execution_result_write_rejected(self) -> None:
        from core.runtime.runtime_mutation_guard import RuntimeMutationRejected, guard_mutation
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource

        with self.assertRaises(RuntimeMutationRejected):
            guard_mutation(
                RuntimeOwner.SCHEDULER,
                RuntimeResource.EXECUTION_RESULT,
                RuntimeAction.WRITE,
            )

    def test_step_executor_execution_result_write_allowed(self) -> None:
        from core.runtime.runtime_mutation_guard import guard_mutation
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource

        request = guard_mutation(
            RuntimeOwner.STEP_EXECUTOR,
            RuntimeResource.EXECUTION_RESULT,
            RuntimeAction.WRITE,
        )

        self.assertTrue(request.allowed)

    def test_step_executor_queue_write_rejected(self) -> None:
        from core.runtime.runtime_mutation_guard import RuntimeMutationRejected, guard_mutation
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource

        with self.assertRaises(RuntimeMutationRejected):
            guard_mutation(
                RuntimeOwner.STEP_EXECUTOR,
                RuntimeResource.QUEUE_STATE,
                RuntimeAction.WRITE,
            )

    def test_orchestrator_dispatch_allowed(self) -> None:
        from core.runtime.runtime_mutation_guard import RuntimeMutationGuard
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource

        request = RuntimeMutationGuard.validate(
            RuntimeOwner.ORCHESTRATOR,
            RuntimeResource.ORCHESTRATION_STATE,
            RuntimeAction.DISPATCH,
        )

        self.assertTrue(request.allowed)

    def test_orchestrator_snapshot_write_rejected(self) -> None:
        from core.runtime.runtime_mutation_guard import RuntimeMutationRejected, guard_mutation
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource

        with self.assertRaises(RuntimeMutationRejected):
            guard_mutation(
                RuntimeOwner.ORCHESTRATOR,
                RuntimeResource.RUNTIME_SNAPSHOT,
                RuntimeAction.WRITE,
            )

    def test_monitor_snapshot_allowed(self) -> None:
        from core.runtime.runtime_mutation_guard import guard_mutation
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource

        request = guard_mutation(
            RuntimeOwner.MONITOR,
            RuntimeResource.RUNTIME_SNAPSHOT,
            RuntimeAction.SNAPSHOT,
        )

        self.assertTrue(request.allowed)

    def test_monitor_execution_result_write_rejected(self) -> None:
        from core.runtime.runtime_mutation_guard import RuntimeMutationRejected, guard_mutation
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource

        with self.assertRaises(RuntimeMutationRejected):
            guard_mutation(
                RuntimeOwner.MONITOR,
                RuntimeResource.EXECUTION_RESULT,
                RuntimeAction.WRITE,
            )

    def test_repair_chain_repair_state_write_allowed(self) -> None:
        from core.runtime.runtime_mutation_guard import guard_mutation
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource

        request = guard_mutation(
            RuntimeOwner.REPAIR_CHAIN,
            RuntimeResource.REPAIR_STATE,
            RuntimeAction.WRITE,
        )

        self.assertTrue(request.allowed)

    def test_repair_chain_queue_write_rejected(self) -> None:
        from core.runtime.runtime_mutation_guard import RuntimeMutationRejected, guard_mutation
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource

        with self.assertRaises(RuntimeMutationRejected):
            guard_mutation(
                RuntimeOwner.REPAIR_CHAIN,
                RuntimeResource.QUEUE_STATE,
                RuntimeAction.WRITE,
            )

    def test_system_write_all_declared_resources_allowed(self) -> None:
        from core.runtime.runtime_mutation_guard import guard_mutation
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource

        for resource in RuntimeResource:
            with self.subTest(resource=resource):
                request = guard_mutation(
                    RuntimeOwner.SYSTEM,
                    resource,
                    RuntimeAction.WRITE,
                )
                self.assertTrue(request.allowed)

    def test_rejected_exception_keeps_request(self) -> None:
        from core.runtime.runtime_mutation_guard import RuntimeMutationRejected, guard_mutation
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource

        with self.assertRaises(RuntimeMutationRejected) as context:
            guard_mutation(
                RuntimeOwner.SCHEDULER,
                RuntimeResource.EXECUTION_RESULT,
                RuntimeAction.WRITE,
            )

        self.assertFalse(context.exception.request.allowed)
        self.assertTrue(context.exception.request.rejected_reason)

    def test_metadata_preserved(self) -> None:
        from core.runtime.runtime_mutation_guard import guard_mutation
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource

        metadata = {"task_id": "task-1", "changes": ["status"]}

        request = guard_mutation(
            RuntimeOwner.SCHEDULER,
            RuntimeResource.QUEUE_STATE,
            RuntimeAction.TRANSITION,
            reason="advance queue",
            metadata=metadata,
        )

        self.assertIs(request.metadata, metadata)
        self.assertEqual(metadata, {"task_id": "task-1", "changes": ["status"]})

    def test_rejected_reason_contains_owner_resource_action(self) -> None:
        from core.runtime.runtime_mutation_guard import RuntimeMutationRejected, guard_mutation
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource

        with self.assertRaises(RuntimeMutationRejected) as context:
            guard_mutation(
                RuntimeOwner.ORCHESTRATOR,
                RuntimeResource.RUNTIME_SNAPSHOT,
                RuntimeAction.WRITE,
            )

        rejected_reason = context.exception.request.rejected_reason or ""

        self.assertIn("owner=", rejected_reason)
        self.assertIn("resource=", rejected_reason)
        self.assertIn("action=", rejected_reason)
        self.assertIn("ORCHESTRATOR", rejected_reason)
        self.assertIn("RUNTIME_SNAPSHOT", rejected_reason)
        self.assertIn("WRITE", rejected_reason)


if __name__ == "__main__":
    unittest.main()
