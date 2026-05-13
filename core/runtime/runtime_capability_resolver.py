from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from typing import Any

from core.runtime.runtime_operation_registry import RuntimeOperationRegistry


@dataclass(frozen=True)
class RuntimeCapability:
    capability_id: str
    operation: str
    target: str
    action: str
    category: str
    risk_level: str
    governance_target: str
    dispatch_target: str
    dispatch_action: str
    metadata: Any
    sequence: int


class RuntimeCapabilityRejected(RuntimeError):
    def __init__(
        self,
        message: str,
        original_exception: BaseException | None = None,
    ) -> None:
        self.original_exception = original_exception
        super().__init__(message)


class RuntimeCapabilityResolver:
    def __init__(self, registry: RuntimeOperationRegistry | None = None) -> None:
        self.registry = registry if registry is not None else RuntimeOperationRegistry()
        self._resolved: list[RuntimeCapability] = []
        self._sequence = 0

    def resolve(self, operation: str) -> RuntimeCapability:
        if not str(operation or "").strip():
            raise RuntimeCapabilityRejected(
                "runtime capability operation is required",
                original_exception=ValueError("operation is required"),
            )

        try:
            runtime_operation = self.registry.get(operation)
        except Exception as exc:
            raise RuntimeCapabilityRejected(
                "runtime capability registry lookup failed",
                original_exception=exc,
            ) from exc

        self._sequence += 1
        capability = RuntimeCapability(
            capability_id=f"capability:{self._sequence}:{operation}",
            operation=runtime_operation.operation,
            target=runtime_operation.target,
            action=runtime_operation.action,
            category=runtime_operation.category,
            risk_level=runtime_operation.risk_level,
            governance_target=runtime_operation.governance_target,
            dispatch_target=runtime_operation.target,
            dispatch_action=runtime_operation.action,
            metadata=copy.deepcopy(runtime_operation.metadata),
            sequence=self._sequence,
        )
        self._resolved.append(capability)
        return self._copy_capability(capability)

    def resolve_many(self, operations: list[str]) -> list[RuntimeCapability]:
        resolved: list[RuntimeCapability] = []
        try:
            for operation in operations:
                resolved.append(self.resolve(operation))
        except RuntimeCapabilityRejected as exc:
            raise RuntimeCapabilityRejected(
                "runtime capability resolve_many failed",
                original_exception=exc,
            ) from exc
        except Exception as exc:
            raise RuntimeCapabilityRejected(
                "runtime capability resolve_many failed",
                original_exception=exc,
            ) from exc

        return resolved

    def get_resolved(self) -> list[RuntimeCapability]:
        return [
            self._copy_capability(capability)
            for capability in self._resolved
        ]

    def clear(self) -> None:
        self._resolved.clear()
        self._sequence = 0

    def _copy_capability(
        self,
        capability: RuntimeCapability,
    ) -> RuntimeCapability:
        return replace(capability, metadata=copy.deepcopy(capability.metadata))
