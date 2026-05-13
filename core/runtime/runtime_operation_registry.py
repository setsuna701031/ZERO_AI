from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from typing import Any


_ALLOWED_RISK_LEVELS = {"low", "medium", "high", "critical"}


@dataclass(frozen=True)
class RuntimeOperation:
    operation: str
    target: str
    action: str
    category: str
    risk_level: str
    governance_target: str
    description: str
    metadata: Any
    sequence: int


class RuntimeOperationRejected(RuntimeError):
    pass


class RuntimeOperationRegistry:
    def __init__(self) -> None:
        self._operations: dict[str, RuntimeOperation] = {}
        self._default_operations: set[str] = set()
        self._sequence = 0
        self._register_default_operations()

    def register(
        self,
        operation: str,
        target: str,
        action: str,
        category: str,
        risk_level: str,
        governance_target: str | None = None,
        description: str | None = None,
        metadata: Any = None,
    ) -> RuntimeOperation:
        operation = self._validate_text("operation", operation)
        target = self._validate_text("target", target)
        action = self._validate_text("action", action)
        category = self._validate_text("category", category)
        risk_level = self._validate_risk_level(risk_level)
        governance_target = (
            target
            if governance_target is None
            else self._validate_text("governance_target", governance_target)
        )
        description = "" if description is None else description

        self._sequence += 1
        registered = RuntimeOperation(
            operation=operation,
            target=target,
            action=action,
            category=category,
            risk_level=risk_level,
            governance_target=governance_target,
            description=description,
            metadata=metadata,
            sequence=self._sequence,
        )
        self._operations[operation] = registered
        return self._copy_operation(registered, preserve_metadata=True)

    def get(self, operation: str) -> RuntimeOperation:
        operation = self._validate_text("operation", operation)
        registered = self._operations.get(operation)
        if registered is None:
            raise RuntimeOperationRejected(
                f"runtime operation unknown operation: {operation!r}"
            )

        return self._copy_operation(registered)

    def list_operations(
        self,
        category: str | None = None,
        governance_target: str | None = None,
        risk_level: str | None = None,
    ) -> list[RuntimeOperation]:
        operations = list(self._operations.values())
        if category is not None:
            operations = [
                operation
                for operation in operations
                if operation.category == category
            ]
        if governance_target is not None:
            operations = [
                operation
                for operation in operations
                if operation.governance_target == governance_target
            ]
        if risk_level is not None:
            operations = [
                operation
                for operation in operations
                if operation.risk_level == risk_level
            ]

        return [self._copy_operation(operation) for operation in operations]

    def has(self, operation: str) -> bool:
        if not str(operation or "").strip():
            return False

        return operation in self._operations

    def unregister(self, operation: str) -> None:
        operation = self._validate_text("operation", operation)
        if operation not in self._operations:
            raise RuntimeOperationRejected(
                f"runtime operation unknown operation: {operation!r}"
            )
        if operation in self._default_operations:
            raise RuntimeOperationRejected(
                f"runtime operation cannot unregister default: {operation!r}"
            )

        del self._operations[operation]

    def clear_custom(self) -> None:
        for operation in list(self._operations):
            if operation not in self._default_operations:
                del self._operations[operation]

    def get_all_mappings(self) -> dict[str, dict[str, Any]]:
        return {
            operation: {
                "target": registered.target,
                "action": registered.action,
                "category": registered.category,
                "risk_level": registered.risk_level,
                "governance_target": registered.governance_target,
                "description": registered.description,
                "metadata": copy.deepcopy(registered.metadata),
                "sequence": registered.sequence,
            }
            for operation, registered in self._operations.items()
        }

    def _register_default_operations(self) -> None:
        defaults = [
            (
                "lifecycle.queue",
                "lifecycle",
                "queue",
                "lifecycle",
                "low",
                "lifecycle",
            ),
            (
                "lifecycle.dispatch",
                "lifecycle",
                "dispatch",
                "lifecycle",
                "low",
                "lifecycle",
            ),
            (
                "lifecycle.start_execution",
                "lifecycle",
                "start_execution",
                "execution",
                "medium",
                "lifecycle",
            ),
            (
                "lifecycle.complete_execution",
                "lifecycle",
                "complete_execution",
                "execution",
                "medium",
                "lifecycle",
            ),
            (
                "lifecycle.fail_execution",
                "lifecycle",
                "fail_execution",
                "execution",
                "medium",
                "lifecycle",
            ),
            ("replay.session", "replay", "session", "replay", "medium", "replay"),
            ("recovery.create", "recovery", "create", "recovery", "high", "recovery"),
            ("recovery.run", "recovery", "run", "recovery", "high", "recovery"),
            (
                "recovery.verify",
                "recovery",
                "verify",
                "recovery",
                "medium",
                "recovery",
            ),
            ("mutation.write", "mutation", "write", "mutation", "high", "mutation"),
            (
                "self_edit.apply",
                "self_edit",
                "apply",
                "self_edit",
                "critical",
                "self_edit",
            ),
        ]
        for default in defaults:
            operation = default[0]
            self.register(*default)
            self._default_operations.add(operation)

    def _validate_risk_level(self, risk_level: str) -> str:
        risk_level = self._validate_text("risk_level", risk_level)
        if risk_level not in _ALLOWED_RISK_LEVELS:
            raise RuntimeOperationRejected(
                f"runtime operation invalid risk_level: {risk_level!r}"
            )

        return risk_level

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise RuntimeOperationRejected(
                f"runtime operation {field_name} is required"
            )

        return value

    def _copy_operation(
        self,
        operation: RuntimeOperation,
        preserve_metadata: bool = False,
    ) -> RuntimeOperation:
        metadata = (
            operation.metadata
            if preserve_metadata
            else copy.deepcopy(operation.metadata)
        )
        return replace(operation, metadata=metadata)
