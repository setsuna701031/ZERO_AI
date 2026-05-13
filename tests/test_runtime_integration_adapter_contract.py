from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeIntegrationAdapterContractTest(unittest.TestCase):
    def _cases(self):
        from core.runtime.runtime_integration_adapter import RuntimeIntegrationAdapter
        from core.runtime.runtime_ownership import RuntimeOwner, RuntimeResource

        return [
            (
                RuntimeIntegrationAdapter.mirror_scheduler_queue_transition,
                "scheduler_queue_transition",
                RuntimeOwner.SCHEDULER,
                RuntimeResource.QUEUE_STATE,
            ),
            (
                RuntimeIntegrationAdapter.mirror_executor_result_write,
                "executor_result_write",
                RuntimeOwner.STEP_EXECUTOR,
                RuntimeResource.EXECUTION_RESULT,
            ),
            (
                RuntimeIntegrationAdapter.mirror_orchestrator_dispatch,
                "orchestrator_dispatch",
                RuntimeOwner.ORCHESTRATOR,
                RuntimeResource.ORCHESTRATION_STATE,
            ),
            (
                RuntimeIntegrationAdapter.mirror_monitor_snapshot,
                "monitor_snapshot",
                RuntimeOwner.MONITOR,
                RuntimeResource.RUNTIME_SNAPSHOT,
            ),
            (
                RuntimeIntegrationAdapter.mirror_repair_incident,
                "repair_incident",
                RuntimeOwner.REPAIR_CHAIN,
                RuntimeResource.RUNTIME_INCIDENT,
            ),
            (
                RuntimeIntegrationAdapter.mirror_repair_state_write,
                "repair_state_write",
                RuntimeOwner.REPAIR_CHAIN,
                RuntimeResource.REPAIR_STATE,
            ),
        ]

    def test_scheduler_queue_transition_mirrors_to_registry_and_bus(self) -> None:
        from core.runtime.runtime_integration_adapter import RuntimeIntegrationAdapter
        from core.runtime.runtime_ownership import RuntimeOwner, RuntimeResource

        result = RuntimeIntegrationAdapter().mirror_scheduler_queue_transition()

        self.assertEqual(result.registry_entry.owner, RuntimeOwner.SCHEDULER)
        self.assertEqual(result.registry_entry.resource, RuntimeResource.QUEUE_STATE)
        self.assertEqual(result.bus_event.event_type, "scheduler_queue_transition")

    def test_executor_result_write_mirrors_to_registry_and_bus(self) -> None:
        from core.runtime.runtime_integration_adapter import RuntimeIntegrationAdapter
        from core.runtime.runtime_ownership import RuntimeOwner, RuntimeResource

        result = RuntimeIntegrationAdapter().mirror_executor_result_write()

        self.assertEqual(result.registry_entry.owner, RuntimeOwner.STEP_EXECUTOR)
        self.assertEqual(result.registry_entry.resource, RuntimeResource.EXECUTION_RESULT)
        self.assertEqual(result.bus_event.event_type, "executor_result_write")

    def test_orchestrator_dispatch_mirrors_to_registry_and_bus(self) -> None:
        from core.runtime.runtime_integration_adapter import RuntimeIntegrationAdapter
        from core.runtime.runtime_ownership import RuntimeOwner, RuntimeResource

        result = RuntimeIntegrationAdapter().mirror_orchestrator_dispatch()

        self.assertEqual(result.registry_entry.owner, RuntimeOwner.ORCHESTRATOR)
        self.assertEqual(
            result.registry_entry.resource,
            RuntimeResource.ORCHESTRATION_STATE,
        )
        self.assertEqual(result.bus_event.event_type, "orchestrator_dispatch")

    def test_monitor_snapshot_mirrors_to_registry_and_bus(self) -> None:
        from core.runtime.runtime_integration_adapter import RuntimeIntegrationAdapter
        from core.runtime.runtime_ownership import RuntimeOwner, RuntimeResource

        result = RuntimeIntegrationAdapter().mirror_monitor_snapshot()

        self.assertEqual(result.registry_entry.owner, RuntimeOwner.MONITOR)
        self.assertEqual(result.registry_entry.resource, RuntimeResource.RUNTIME_SNAPSHOT)
        self.assertEqual(result.bus_event.event_type, "monitor_snapshot")

    def test_repair_incident_mirrors_to_registry_and_bus(self) -> None:
        from core.runtime.runtime_integration_adapter import RuntimeIntegrationAdapter
        from core.runtime.runtime_ownership import RuntimeOwner, RuntimeResource

        result = RuntimeIntegrationAdapter().mirror_repair_incident()

        self.assertEqual(result.registry_entry.owner, RuntimeOwner.REPAIR_CHAIN)
        self.assertEqual(result.registry_entry.resource, RuntimeResource.RUNTIME_INCIDENT)
        self.assertEqual(result.bus_event.event_type, "repair_incident")

    def test_repair_state_write_mirrors_to_registry_and_bus(self) -> None:
        from core.runtime.runtime_integration_adapter import RuntimeIntegrationAdapter
        from core.runtime.runtime_ownership import RuntimeOwner, RuntimeResource

        result = RuntimeIntegrationAdapter().mirror_repair_state_write()

        self.assertEqual(result.registry_entry.owner, RuntimeOwner.REPAIR_CHAIN)
        self.assertEqual(result.registry_entry.resource, RuntimeResource.REPAIR_STATE)
        self.assertEqual(result.bus_event.event_type, "repair_state_write")

    def test_payload_preserved(self) -> None:
        from core.runtime.runtime_integration_adapter import RuntimeIntegrationAdapter

        payload = {"task_id": "task-1", "status": "queued"}

        result = RuntimeIntegrationAdapter().mirror_scheduler_queue_transition(
            payload=payload
        )

        self.assertIs(result.payload, payload)
        self.assertIs(result.boundary_request.payload, payload)
        self.assertIs(result.registry_entry.payload, payload)
        self.assertIs(result.bus_event.payload, payload)

    def test_metadata_preserved(self) -> None:
        from core.runtime.runtime_integration_adapter import RuntimeIntegrationAdapter

        metadata = {"source": "contract", "attempt": 1}

        result = RuntimeIntegrationAdapter().mirror_scheduler_queue_transition(
            metadata=metadata
        )

        self.assertIs(result.metadata, metadata)
        self.assertIs(result.boundary_request.metadata, metadata)
        self.assertIs(result.registry_entry.metadata, metadata)
        self.assertIs(result.bus_event.metadata, metadata)

    def test_registry_sequence_increments(self) -> None:
        from core.runtime.runtime_integration_adapter import RuntimeIntegrationAdapter

        adapter = RuntimeIntegrationAdapter()
        first = adapter.mirror_scheduler_queue_transition()
        second = adapter.mirror_executor_result_write()

        self.assertEqual(first.registry_entry.sequence, 1)
        self.assertEqual(second.registry_entry.sequence, 2)

    def test_bus_sequence_increments(self) -> None:
        from core.runtime.runtime_integration_adapter import RuntimeIntegrationAdapter

        adapter = RuntimeIntegrationAdapter()
        first = adapter.mirror_scheduler_queue_transition()
        second = adapter.mirror_executor_result_write()

        self.assertEqual(first.bus_event.sequence, 1)
        self.assertEqual(second.bus_event.sequence, 2)

    def test_custom_registry_and_bus_can_be_injected(self) -> None:
        from core.runtime.runtime_event_bus import RuntimeEventBus
        from core.runtime.runtime_integration_adapter import RuntimeIntegrationAdapter
        from core.runtime.runtime_state_registry import RuntimeStateRegistry

        registry = RuntimeStateRegistry()
        event_bus = RuntimeEventBus()
        adapter = RuntimeIntegrationAdapter(registry=registry, event_bus=event_bus)

        result = adapter.mirror_scheduler_queue_transition()

        self.assertEqual(registry.snapshot().entries, [result.registry_entry])
        self.assertEqual(event_bus.get_events(), [result.bus_event])

    def test_bus_event_channel_is_runtime_integration(self) -> None:
        from core.runtime.runtime_integration_adapter import RuntimeIntegrationAdapter

        result = RuntimeIntegrationAdapter().mirror_scheduler_queue_transition()

        self.assertEqual(result.bus_event.channel, "runtime.integration")

    def test_bus_event_type_matches_operation(self) -> None:
        from core.runtime.runtime_integration_adapter import RuntimeIntegrationAdapter

        adapter = RuntimeIntegrationAdapter()

        for method, operation, _owner, _resource in self._cases():
            with self.subTest(operation=operation):
                result = method(adapter)
                self.assertEqual(result.operation, operation)
                self.assertEqual(result.bus_event.event_type, operation)

    def test_adapter_result_includes_boundary_request_registry_entry_bus_event(
        self,
    ) -> None:
        from core.runtime.runtime_boundary import RuntimeBoundaryRequest
        from core.runtime.runtime_event_bus import RuntimeBusEvent
        from core.runtime.runtime_integration_adapter import RuntimeIntegrationAdapter
        from core.runtime.runtime_state_registry import RuntimeStateEntry

        result = RuntimeIntegrationAdapter().mirror_scheduler_queue_transition()

        self.assertIsInstance(result.boundary_request, RuntimeBoundaryRequest)
        self.assertIsInstance(result.registry_entry, RuntimeStateEntry)
        self.assertIsInstance(result.bus_event, RuntimeBusEvent)

    def test_adapter_does_not_mutate_payload_or_metadata(self) -> None:
        from core.runtime.runtime_integration_adapter import RuntimeIntegrationAdapter

        payload = {"items": [{"task_id": "task-1", "state": "queued"}]}
        metadata = {"tags": ["contract"], "attempt": 1}
        payload_before = copy.deepcopy(payload)
        metadata_before = copy.deepcopy(metadata)

        RuntimeIntegrationAdapter().mirror_scheduler_queue_transition(
            payload=payload,
            metadata=metadata,
        )

        self.assertEqual(payload, payload_before)
        self.assertEqual(metadata, metadata_before)

    def test_all_operations_use_expected_owner_and_registry_resource(self) -> None:
        from core.runtime.runtime_integration_adapter import RuntimeIntegrationAdapter

        adapter = RuntimeIntegrationAdapter()

        for method, operation, owner, resource in self._cases():
            with self.subTest(operation=operation):
                result = method(adapter)
                self.assertTrue(result.boundary_request.allowed)
                self.assertEqual(result.boundary_request.owner, owner)
                self.assertEqual(result.boundary_request.resource, resource)
                self.assertEqual(result.registry_entry.owner, owner)
                self.assertEqual(result.registry_entry.operation, operation)
                self.assertEqual(result.registry_entry.resource, resource)

    def test_rejected_keeps_original_exception(self) -> None:
        from core.runtime.runtime_integration_adapter import (
            RuntimeAdapterRejected,
            RuntimeIntegrationAdapter,
        )

        class FailingBus:
            def publish(self, *_args, **_kwargs):
                raise ValueError("boom")

        with self.assertRaises(RuntimeAdapterRejected) as context:
            RuntimeIntegrationAdapter(
                event_bus=FailingBus()
            ).mirror_scheduler_queue_transition()

        self.assertIsInstance(context.exception.original_exception, ValueError)


if __name__ == "__main__":
    unittest.main()
