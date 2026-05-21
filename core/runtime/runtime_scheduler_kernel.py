from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class RuntimeScheduledOperation:
    operation_id: str
    operation_type: str
    transaction_id: str = ""
    checkpoint_id: str = ""
    capability_node_id: str = ""
    intent_id: str = ""
    risk: str = "low"
    recovery_aware: bool = True
    replay_aware: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.operation_id or "").strip():
            raise ValueError("runtime_scheduled_operation_id_required")
        if not str(self.operation_type or "").strip():
            raise ValueError("runtime_scheduled_operation_type_required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "transaction_id": self.transaction_id,
            "checkpoint_id": self.checkpoint_id,
            "capability_node_id": self.capability_node_id,
            "intent_id": self.intent_id,
            "risk": self.risk,
            "recovery_aware": self.recovery_aware,
            "replay_aware": self.replay_aware,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RuntimeExecutionQueue:
    operations: tuple[RuntimeScheduledOperation, ...] = ()

    def enqueue(self, operation: RuntimeScheduledOperation) -> "RuntimeExecutionQueue":
        if not operation.transaction_id:
            raise ValueError("runtime_scheduled_operation_requires_transaction")
        if not operation.checkpoint_id:
            raise ValueError("runtime_scheduled_operation_requires_checkpoint")
        if not operation.capability_node_id:
            raise ValueError("runtime_scheduled_operation_requires_capability")
        if not operation.intent_id:
            raise ValueError("runtime_scheduled_operation_requires_intent")
        return replace(self, operations=(*self.operations, operation))

    def dispatch_next(self) -> tuple[RuntimeScheduledOperation | None, "RuntimeExecutionQueue"]:
        if not self.operations:
            return None, self
        return self.operations[0], replace(self, operations=self.operations[1:])

    def to_dict(self) -> dict[str, Any]:
        return {"operations": [item.to_dict() for item in self.operations]}


__all__ = ["RuntimeExecutionQueue", "RuntimeScheduledOperation"]
