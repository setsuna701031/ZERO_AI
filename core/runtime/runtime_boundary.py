from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.runtime.runtime_mutation_guard import RuntimeMutationRejected, guard_mutation
from core.runtime.runtime_ownership import RuntimeAction, RuntimeResource


@dataclass(frozen=True)
class RuntimeBoundaryRequest:
    owner: Any
    operation: str
    resource: Any
    action: Any
    allowed: bool
    payload: Any = None
    metadata: Any = None
    rejected_reason: str | None = None


class RuntimeBoundaryRejected(PermissionError):
    def __init__(self, request: RuntimeBoundaryRequest) -> None:
        self.request = request
        super().__init__(request.rejected_reason)


class RuntimeBoundary:
    def request_queue_transition(
        self,
        owner: Any,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeBoundaryRequest:
        return self._request(
            owner=owner,
            operation="queue_transition",
            resource=RuntimeResource.QUEUE_STATE,
            action=RuntimeAction.TRANSITION,
            payload=payload,
            metadata=metadata,
        )

    def request_execution_result_write(
        self,
        owner: Any,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeBoundaryRequest:
        return self._request(
            owner=owner,
            operation="execution_result_write",
            resource=RuntimeResource.EXECUTION_RESULT,
            action=RuntimeAction.WRITE,
            payload=payload,
            metadata=metadata,
        )

    def request_orchestration_dispatch(
        self,
        owner: Any,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeBoundaryRequest:
        return self._request(
            owner=owner,
            operation="orchestration_dispatch",
            resource=RuntimeResource.ORCHESTRATION_STATE,
            action=RuntimeAction.DISPATCH,
            payload=payload,
            metadata=metadata,
        )

    def request_runtime_snapshot(
        self,
        owner: Any,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeBoundaryRequest:
        return self._request(
            owner=owner,
            operation="runtime_snapshot",
            resource=RuntimeResource.RUNTIME_SNAPSHOT,
            action=RuntimeAction.SNAPSHOT,
            payload=payload,
            metadata=metadata,
        )

    def emit_runtime_event(
        self,
        owner: Any,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeBoundaryRequest:
        return self._request(
            owner=owner,
            operation="runtime_event_emit",
            resource=RuntimeResource.RUNTIME_EVENT,
            action=RuntimeAction.EMIT,
            payload=payload,
            metadata=metadata,
        )

    def emit_runtime_incident(
        self,
        owner: Any,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeBoundaryRequest:
        return self._request(
            owner=owner,
            operation="runtime_incident_emit",
            resource=RuntimeResource.RUNTIME_INCIDENT,
            action=RuntimeAction.EMIT,
            payload=payload,
            metadata=metadata,
        )

    def _request(
        self,
        owner: Any,
        operation: str,
        resource: RuntimeResource,
        action: RuntimeAction,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeBoundaryRequest:
        try:
            mutation_request = guard_mutation(
                owner=owner,
                resource=resource,
                action=action,
                reason=operation,
                metadata=metadata,
            )
        except RuntimeMutationRejected as exc:
            rejected_reason = (
                "runtime boundary rejected: "
                f"owner={owner!r}, resource={resource!r}, "
                f"action={action!r}, operation={operation!r}"
            )
            request = RuntimeBoundaryRequest(
                owner=owner,
                operation=operation,
                resource=resource,
                action=action,
                allowed=False,
                payload=payload,
                metadata=metadata,
                rejected_reason=rejected_reason,
            )
            raise RuntimeBoundaryRejected(request) from exc

        return RuntimeBoundaryRequest(
            owner=mutation_request.owner,
            operation=operation,
            resource=mutation_request.resource,
            action=mutation_request.action,
            allowed=True,
            payload=payload,
            metadata=metadata,
            rejected_reason=None,
        )
