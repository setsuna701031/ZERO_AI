from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


_ALLOWED_RISK_LEVELS = {"low", "medium", "high", "critical"}


@dataclass(frozen=True)
class RuntimeIntent:
    intent_id: str
    operation: str
    target: str
    action: str
    category: str
    risk_level: str
    governance_target: str
    payload: Any
    metadata: Any
    sequence: int


@dataclass(frozen=True)
class _RuntimeIntentMapping:
    target: str
    action: str
    category: str
    risk_level: str
    governance_target: str


class RuntimeIntentRejected(RuntimeError):
    pass


class RuntimeIntentClassifier:
    def __init__(self) -> None:
        self._mappings: dict[str, _RuntimeIntentMapping] = {}
        self._intents: list[RuntimeIntent] = []
        self._sequence = 0
        self._register_default_mappings()

    def classify(
        self,
        operation: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeIntent:
        operation = self._validate_text("operation", operation)
        mapping = self._mappings.get(operation)
        if mapping is None:
            raise RuntimeIntentRejected(
                f"runtime intent unknown operation: {operation!r}"
            )

        self._sequence += 1
        intent = RuntimeIntent(
            intent_id=f"intent:{self._sequence}:{operation}",
            operation=operation,
            target=mapping.target,
            action=mapping.action,
            category=mapping.category,
            risk_level=mapping.risk_level,
            governance_target=mapping.governance_target,
            payload=payload,
            metadata=metadata,
            sequence=self._sequence,
        )
        self._intents.append(intent)
        return self._copy_intent(intent)

    def register_mapping(
        self,
        operation: str,
        target: str,
        action: str,
        category: str,
        risk_level: str,
        governance_target: str | None = None,
    ) -> None:
        operation = self._validate_text("operation", operation)
        target = self._validate_text("target", target)
        action = self._validate_text("action", action)
        category = self._validate_text("category", category)
        risk_level = self._validate_risk_level(risk_level)
        if governance_target is None:
            governance_target = target
        else:
            governance_target = self._validate_text(
                "governance_target",
                governance_target,
            )

        self._mappings[operation] = _RuntimeIntentMapping(
            target=target,
            action=action,
            category=category,
            risk_level=risk_level,
            governance_target=governance_target,
        )

    def get_mappings(self) -> dict[str, dict[str, str]]:
        return {
            operation: {
                "target": mapping.target,
                "action": mapping.action,
                "category": mapping.category,
                "risk_level": mapping.risk_level,
                "governance_target": mapping.governance_target,
            }
            for operation, mapping in self._mappings.items()
        }

    def get_intents(self) -> list[RuntimeIntent]:
        return [self._copy_intent(intent) for intent in self._intents]

    def clear_intents(self) -> None:
        self._intents.clear()
        self._sequence = 0

    def _register_default_mappings(self) -> None:
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
            self.register_mapping(*default)

    def _validate_risk_level(self, risk_level: str) -> str:
        risk_level = self._validate_text("risk_level", risk_level)
        if risk_level not in _ALLOWED_RISK_LEVELS:
            raise RuntimeIntentRejected(
                f"runtime intent invalid risk_level: {risk_level!r}"
            )

        return risk_level

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise RuntimeIntentRejected(
                f"runtime intent {field_name} is required"
            )

        return value

    def _copy_intent(self, intent: RuntimeIntent) -> RuntimeIntent:
        return replace(intent)
