from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.runtime.runtime_boundary import RuntimeBoundaryRequest
from core.runtime.runtime_mutation_guard import RuntimeMutationRejected, guard_mutation


@dataclass(frozen=True)
class RuntimeStateEntry:
    owner: Any
    resource: Any
    action: Any
    operation: str
    payload: Any
    metadata: Any
    sequence: int


@dataclass(frozen=True)
class RuntimeStateSnapshot:
    entries: list[RuntimeStateEntry]
    sequence: int
    buckets: dict[Any, list[RuntimeStateEntry]]


class RuntimeStateRegistryRejected(PermissionError):
    def __init__(self, message: str, request: Any = None) -> None:
        self.request = request
        super().__init__(message)


class RuntimeStateRegistry:
    def __init__(self) -> None:
        self._entries: list[RuntimeStateEntry] = []
        self._buckets: dict[Any, list[RuntimeStateEntry]] = {}
        self._sequence = 0

    def apply_boundary_request(
        self,
        request: RuntimeBoundaryRequest,
    ) -> RuntimeStateEntry:
        if not request.allowed:
            raise RuntimeStateRegistryRejected(
                "runtime state registry rejected boundary request",
                request=request,
            )

        return self._append(
            owner=request.owner,
            operation=request.operation,
            resource=request.resource,
            action=request.action,
            payload=request.payload,
            metadata=request.metadata,
        )

    def record(
        self,
        owner: Any,
        operation: str,
        resource: Any,
        action: Any,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeStateEntry:
        try:
            guard_mutation(
                owner=owner,
                resource=resource,
                action=action,
                reason=operation,
                metadata=metadata,
            )
        except RuntimeMutationRejected as exc:
            raise RuntimeStateRegistryRejected(
                "runtime state registry mutation rejected",
                request=exc.request,
            ) from exc

        return self._append(
            owner=owner,
            operation=operation,
            resource=resource,
            action=action,
            payload=payload,
            metadata=metadata,
        )

    def get_bucket(self, resource: Any) -> list[RuntimeStateEntry]:
        return list(self._buckets.get(resource, []))

    def snapshot(self) -> RuntimeStateSnapshot:
        return RuntimeStateSnapshot(
            entries=list(self._entries),
            sequence=self._sequence,
            buckets={
                resource: list(entries)
                for resource, entries in self._buckets.items()
            },
        )

    def clear(self) -> None:
        self._entries.clear()
        self._buckets.clear()
        self._sequence = 0

    def _append(
        self,
        owner: Any,
        operation: str,
        resource: Any,
        action: Any,
        payload: Any,
        metadata: Any,
    ) -> RuntimeStateEntry:
        self._sequence += 1
        entry = RuntimeStateEntry(
            owner=owner,
            resource=resource,
            action=action,
            operation=operation,
            payload=payload,
            metadata=metadata,
            sequence=self._sequence,
        )
        self._entries.append(entry)
        self._buckets.setdefault(resource, []).append(entry)
        return entry
