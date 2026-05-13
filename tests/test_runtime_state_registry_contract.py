from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeStateRegistryContractTest(unittest.TestCase):
    def test_scheduler_queue_transition_records_entry(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource
        from core.runtime.runtime_state_registry import RuntimeStateRegistry

        entry = RuntimeStateRegistry().record(
            RuntimeOwner.SCHEDULER,
            "queue_transition",
            RuntimeResource.QUEUE_STATE,
            RuntimeAction.TRANSITION,
        )

        self.assertEqual(entry.owner, RuntimeOwner.SCHEDULER)
        self.assertEqual(entry.sequence, 1)

    def test_step_executor_execution_result_records_entry(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource
        from core.runtime.runtime_state_registry import RuntimeStateRegistry

        entry = RuntimeStateRegistry().record(
            RuntimeOwner.STEP_EXECUTOR,
            "execution_result_write",
            RuntimeResource.EXECUTION_RESULT,
            RuntimeAction.WRITE,
        )

        self.assertEqual(entry.resource, RuntimeResource.EXECUTION_RESULT)

    def test_orchestrator_dispatch_records_entry(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource
        from core.runtime.runtime_state_registry import RuntimeStateRegistry

        entry = RuntimeStateRegistry().record(
            RuntimeOwner.ORCHESTRATOR,
            "orchestration_dispatch",
            RuntimeResource.ORCHESTRATION_STATE,
            RuntimeAction.DISPATCH,
        )

        self.assertEqual(entry.action, RuntimeAction.DISPATCH)

    def test_monitor_snapshot_records_entry(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource
        from core.runtime.runtime_state_registry import RuntimeStateRegistry

        entry = RuntimeStateRegistry().record(
            RuntimeOwner.MONITOR,
            "runtime_snapshot",
            RuntimeResource.RUNTIME_SNAPSHOT,
            RuntimeAction.SNAPSHOT,
        )

        self.assertEqual(entry.operation, "runtime_snapshot")

    def test_repair_chain_repair_state_records_entry(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource
        from core.runtime.runtime_state_registry import RuntimeStateRegistry

        entry = RuntimeStateRegistry().record(
            RuntimeOwner.REPAIR_CHAIN,
            "repair_state_write",
            RuntimeResource.REPAIR_STATE,
            RuntimeAction.WRITE,
        )

        self.assertEqual(entry.resource, RuntimeResource.REPAIR_STATE)

    def test_illegal_scheduler_execution_result_write_rejected(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource
        from core.runtime.runtime_state_registry import (
            RuntimeStateRegistry,
            RuntimeStateRegistryRejected,
        )

        with self.assertRaises(RuntimeStateRegistryRejected):
            RuntimeStateRegistry().record(
                RuntimeOwner.SCHEDULER,
                "execution_result_write",
                RuntimeResource.EXECUTION_RESULT,
                RuntimeAction.WRITE,
            )

    def test_illegal_step_executor_queue_write_rejected(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource
        from core.runtime.runtime_state_registry import (
            RuntimeStateRegistry,
            RuntimeStateRegistryRejected,
        )

        with self.assertRaises(RuntimeStateRegistryRejected):
            RuntimeStateRegistry().record(
                RuntimeOwner.STEP_EXECUTOR,
                "queue_write",
                RuntimeResource.QUEUE_STATE,
                RuntimeAction.WRITE,
            )

    def test_apply_rejected_boundary_request_raises(self) -> None:
        from core.runtime.runtime_boundary import RuntimeBoundaryRequest
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource
        from core.runtime.runtime_state_registry import (
            RuntimeStateRegistry,
            RuntimeStateRegistryRejected,
        )

        request = RuntimeBoundaryRequest(
            owner=RuntimeOwner.SCHEDULER,
            operation="execution_result_write",
            resource=RuntimeResource.EXECUTION_RESULT,
            action=RuntimeAction.WRITE,
            allowed=False,
            rejected_reason="denied",
        )

        with self.assertRaises(RuntimeStateRegistryRejected):
            RuntimeStateRegistry().apply_boundary_request(request)

    def test_sequence_increments_from_1(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource
        from core.runtime.runtime_state_registry import RuntimeStateRegistry

        registry = RuntimeStateRegistry()
        first = registry.record(
            RuntimeOwner.SCHEDULER,
            "queue_transition",
            RuntimeResource.QUEUE_STATE,
            RuntimeAction.TRANSITION,
        )
        second = registry.record(
            RuntimeOwner.SCHEDULER,
            "runtime_event_emit",
            RuntimeResource.RUNTIME_EVENT,
            RuntimeAction.EMIT,
        )

        self.assertEqual(first.sequence, 1)
        self.assertEqual(second.sequence, 2)

    def test_bucket_returns_only_matching_resource(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource
        from core.runtime.runtime_state_registry import RuntimeStateRegistry

        registry = RuntimeStateRegistry()
        registry.record(
            RuntimeOwner.SCHEDULER,
            "queue_transition",
            RuntimeResource.QUEUE_STATE,
            RuntimeAction.TRANSITION,
        )
        registry.record(
            RuntimeOwner.SCHEDULER,
            "runtime_event_emit",
            RuntimeResource.RUNTIME_EVENT,
            RuntimeAction.EMIT,
        )

        bucket = registry.get_bucket(RuntimeResource.QUEUE_STATE)

        self.assertEqual(len(bucket), 1)
        self.assertEqual(bucket[0].resource, RuntimeResource.QUEUE_STATE)

    def test_bucket_returns_copy(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource
        from core.runtime.runtime_state_registry import RuntimeStateRegistry

        registry = RuntimeStateRegistry()
        registry.record(
            RuntimeOwner.SCHEDULER,
            "queue_transition",
            RuntimeResource.QUEUE_STATE,
            RuntimeAction.TRANSITION,
        )

        bucket = registry.get_bucket(RuntimeResource.QUEUE_STATE)
        bucket.clear()

        self.assertEqual(len(registry.get_bucket(RuntimeResource.QUEUE_STATE)), 1)

    def test_snapshot_returns_copy(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource
        from core.runtime.runtime_state_registry import RuntimeStateRegistry

        registry = RuntimeStateRegistry()
        registry.record(
            RuntimeOwner.SCHEDULER,
            "queue_transition",
            RuntimeResource.QUEUE_STATE,
            RuntimeAction.TRANSITION,
        )

        snapshot = registry.snapshot()
        snapshot.entries.clear()
        snapshot.buckets[RuntimeResource.QUEUE_STATE].clear()

        self.assertEqual(len(registry.snapshot().entries), 1)
        self.assertEqual(len(registry.get_bucket(RuntimeResource.QUEUE_STATE)), 1)

    def test_clear_resets_registry_and_sequence(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource
        from core.runtime.runtime_state_registry import RuntimeStateRegistry

        registry = RuntimeStateRegistry()
        registry.record(
            RuntimeOwner.SCHEDULER,
            "queue_transition",
            RuntimeResource.QUEUE_STATE,
            RuntimeAction.TRANSITION,
        )
        registry.clear()
        entry = registry.record(
            RuntimeOwner.SCHEDULER,
            "queue_transition",
            RuntimeResource.QUEUE_STATE,
            RuntimeAction.TRANSITION,
        )

        self.assertEqual(entry.sequence, 1)
        self.assertEqual(len(registry.snapshot().entries), 1)

    def test_payload_preserved(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource
        from core.runtime.runtime_state_registry import RuntimeStateRegistry

        payload = {"task_id": "task-1"}
        entry = RuntimeStateRegistry().record(
            RuntimeOwner.SCHEDULER,
            "queue_transition",
            RuntimeResource.QUEUE_STATE,
            RuntimeAction.TRANSITION,
            payload=payload,
        )

        self.assertIs(entry.payload, payload)

    def test_metadata_preserved(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource
        from core.runtime.runtime_state_registry import RuntimeStateRegistry

        metadata = {"source": "contract"}
        entry = RuntimeStateRegistry().record(
            RuntimeOwner.SCHEDULER,
            "queue_transition",
            RuntimeResource.QUEUE_STATE,
            RuntimeAction.TRANSITION,
            metadata=metadata,
        )

        self.assertIs(entry.metadata, metadata)

    def test_system_can_record_all_declared_resources_actions(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource
        from core.runtime.runtime_state_registry import RuntimeStateRegistry

        registry = RuntimeStateRegistry()

        for resource in RuntimeResource:
            for action in RuntimeAction:
                with self.subTest(resource=resource, action=action):
                    entry = registry.record(
                        RuntimeOwner.SYSTEM,
                        "system_record",
                        resource,
                        action,
                    )
                    self.assertEqual(entry.owner, RuntimeOwner.SYSTEM)


if __name__ == "__main__":
    unittest.main()
