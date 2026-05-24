from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.runtime.runtime_boundary import RuntimeBoundary, RuntimeBoundaryRequest
from core.runtime.runtime_event_bus import RuntimeBusEvent, RuntimeEventBus
from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource
from core.runtime.runtime_state_registry import RuntimeStateEntry, RuntimeStateRegistry


RUNTIME_INTEGRATION_CHANNEL = "runtime.integration"


@dataclass(frozen=True)
class RuntimeAdapterResult:
    source: str
    operation: str
    boundary_request: RuntimeBoundaryRequest
    registry_entry: RuntimeStateEntry
    bus_event: RuntimeBusEvent
    payload: Any
    metadata: Any


class RuntimeAdapterRejected(RuntimeError):
    def __init__(
        self,
        message: str,
        original_exception: BaseException,
    ) -> None:
        self.original_exception = original_exception
        super().__init__(message)


class RuntimeIntegrationAdapter:
    """Read-only mirror adapter for runtime integration surfaces.

    Contract notes:
    - payload and metadata object identity must be preserved.
    - adapter must not inject canonical/runtime fields into caller payload.
    - boundary / registry / bus receive the exact same payload and metadata
      objects that the caller passed in.
    """

    def __init__(
        self,
        registry: RuntimeStateRegistry | None = None,
        event_bus: RuntimeEventBus | None = None,
    ) -> None:
        self.boundary = RuntimeBoundary()
        self.registry = registry if registry is not None else RuntimeStateRegistry()
        self.event_bus = event_bus if event_bus is not None else RuntimeEventBus()

    def mirror_scheduler_queue_transition(
        self,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeAdapterResult:
        return self._mirror(
            source="scheduler",
            owner=RuntimeOwner.SCHEDULER,
            operation="scheduler_queue_transition",
            registry_resource=RuntimeResource.QUEUE_STATE,
            registry_action=RuntimeAction.TRANSITION,
            payload=payload,
            metadata=metadata,
        )

    def mirror_executor_result_write(
        self,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeAdapterResult:
        return self._mirror(
            source="step_executor",
            owner=RuntimeOwner.STEP_EXECUTOR,
            operation="executor_result_write",
            registry_resource=RuntimeResource.EXECUTION_RESULT,
            registry_action=RuntimeAction.WRITE,
            payload=payload,
            metadata=metadata,
        )

    def mirror_orchestrator_dispatch(
        self,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeAdapterResult:
        return self._mirror(
            source="orchestrator",
            owner=RuntimeOwner.ORCHESTRATOR,
            operation="orchestrator_dispatch",
            registry_resource=RuntimeResource.ORCHESTRATION_STATE,
            registry_action=RuntimeAction.DISPATCH,
            payload=payload,
            metadata=metadata,
        )

    def mirror_monitor_snapshot(
        self,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeAdapterResult:
        return self._mirror(
            source="monitor",
            owner=RuntimeOwner.MONITOR,
            operation="monitor_snapshot",
            registry_resource=RuntimeResource.RUNTIME_SNAPSHOT,
            registry_action=RuntimeAction.SNAPSHOT,
            payload=payload,
            metadata=metadata,
        )

    def mirror_repair_incident(
        self,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeAdapterResult:
        return self._mirror(
            source="repair_chain",
            owner=RuntimeOwner.REPAIR_CHAIN,
            operation="repair_incident",
            registry_resource=RuntimeResource.RUNTIME_INCIDENT,
            registry_action=RuntimeAction.EMIT,
            payload=payload,
            metadata=metadata,
        )

    def mirror_repair_state_write(
        self,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeAdapterResult:
        return self._mirror(
            source="repair_chain",
            owner=RuntimeOwner.REPAIR_CHAIN,
            operation="repair_state_write",
            registry_resource=RuntimeResource.REPAIR_STATE,
            registry_action=RuntimeAction.WRITE,
            payload=payload,
            metadata=metadata,
        )

    def _make_boundary_request(
        self,
        *,
        owner: RuntimeOwner,
        operation: str,
        resource: RuntimeResource,
        action: RuntimeAction,
        payload: Any,
        metadata: Any,
    ) -> RuntimeBoundaryRequest:
        request_fn = getattr(self.boundary, "_request", None)
        if not callable(request_fn):
            raise RuntimeError("runtime boundary does not expose _request")

        return request_fn(
            owner=owner,
            operation=operation,
            resource=resource,
            action=action,
            payload=payload,
            metadata=metadata,
        )

    def _mirror(
        self,
        source: str,
        owner: RuntimeOwner,
        operation: str,
        registry_resource: RuntimeResource,
        registry_action: RuntimeAction,
        payload: Any,
        metadata: Any,
    ) -> RuntimeAdapterResult:
        try:
            request = self._make_boundary_request(
                owner=owner,
                operation=operation,
                resource=registry_resource,
                action=registry_action,
                payload=payload,
                metadata=metadata,
            )

            entry = self.registry.record(
                owner=owner,
                operation=operation,
                resource=registry_resource,
                action=registry_action,
                payload=payload,
                metadata=metadata,
            )

            event = self.event_bus.publish(
                RUNTIME_INTEGRATION_CHANNEL,
                operation,
                payload=payload,
                metadata=metadata,
            )

        except Exception as exc:
            raise RuntimeAdapterRejected(
                "runtime integration adapter rejected mirror operation",
                original_exception=exc,
            ) from exc

        return RuntimeAdapterResult(
            source=source,
            operation=operation,
            boundary_request=request,
            registry_entry=entry,
            bus_event=event,
            payload=payload,
            metadata=metadata,
        )
