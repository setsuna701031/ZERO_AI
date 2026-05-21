from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


class RuntimeRiskClassification(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class RuntimeIntent:
    intent_id: str
    description: str
    category: str
    requested_paths: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "description": self.description,
            "category": self.category,
            "requested_paths": list(self.requested_paths),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RuntimeIntentEvaluation:
    intent: RuntimeIntent
    allowed: bool
    risk: RuntimeRiskClassification
    reason: str
    requires_governance: bool
    recursive_mutation_allowed: bool = False
    self_edit_allowed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_version": RUNTIME_KERNEL_VERSION,
            "abi_version": RUNTIME_ABI_VERSION,
            "artifact_type": "runtime_intent_governance",
            "intent": self.intent.to_dict(),
            "allowed": self.allowed,
            "risk": self.risk.value,
            "reason": self.reason,
            "requires_governance": self.requires_governance,
            "recursive_mutation_allowed": self.recursive_mutation_allowed,
            "self_edit_allowed": self.self_edit_allowed,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RuntimeIntentPolicy:
    allow_recursive_repair: bool = False
    allow_self_edit: bool = False
    allow_high_risk_runtime_mutation: bool = False

    def evaluate(self, intent: RuntimeIntent) -> RuntimeIntentEvaluation:
        category = intent.category
        risk = _risk_for_intent(intent)
        requires_governance = category != "low-risk execution" or risk in {
            RuntimeRiskClassification.HIGH,
            RuntimeRiskClassification.CRITICAL,
        }
        if category == "recursive repair" and not self.allow_recursive_repair:
            return RuntimeIntentEvaluation(
                intent=intent,
                allowed=False,
                risk=risk,
                reason="recursive_repair_requires_policy_grant",
                requires_governance=True,
            )
        if category == "self-edit" and not self.allow_self_edit:
            return RuntimeIntentEvaluation(
                intent=intent,
                allowed=False,
                risk=risk,
                reason="self_edit_requires_policy_grant",
                requires_governance=True,
            )
        if (
            category == "high-risk runtime mutation"
            and not self.allow_high_risk_runtime_mutation
            and risk == RuntimeRiskClassification.CRITICAL
        ):
            return RuntimeIntentEvaluation(
                intent=intent,
                allowed=False,
                risk=risk,
                reason="critical_runtime_mutation_requires_policy_grant",
                requires_governance=True,
            )
        return RuntimeIntentEvaluation(
            intent=intent,
            allowed=True,
            risk=risk,
            reason="intent_allowed_with_governance" if requires_governance else "intent_allowed",
            requires_governance=requires_governance,
            recursive_mutation_allowed=self.allow_recursive_repair,
            self_edit_allowed=self.allow_self_edit,
        )


def classify_runtime_intent(
    *,
    description: str,
    requested_paths: tuple[str, ...] = (),
    risk_level: str = "medium",
    metadata: dict[str, Any] | None = None,
) -> RuntimeIntent:
    text = str(description or "").lower()
    paths = tuple(str(path).replace("\\", "/") for path in requested_paths)
    category = "low-risk execution"
    if any(token in text for token in ("recursive", "loop repair")):
        category = "recursive repair"
    elif any(token in text for token in ("self-edit", "self edit", "self_edit")):
        category = "self-edit"
    elif any(path.startswith("core/runtime/") for path in paths) and str(risk_level).lower() in {"high", "critical"}:
        category = "high-risk runtime mutation"
    elif any(token in text for token in ("repair", "recover")):
        category = "autonomous repair"
    elif paths:
        category = "governed mutation"
    return RuntimeIntent(
        intent_id="runtime-intent-" + str(abs(hash((description, paths, risk_level))))[:16],
        description=str(description or ""),
        category=category,
        requested_paths=paths,
        metadata={"risk_level": str(risk_level), **dict(metadata or {})},
    )


def _risk_for_intent(intent: RuntimeIntent) -> RuntimeRiskClassification:
    explicit = str(intent.metadata.get("risk_level") or "").lower()
    if explicit in RuntimeRiskClassification._value2member_map_:
        return RuntimeRiskClassification(explicit)
    if intent.category in {"self-edit", "high-risk runtime mutation"}:
        return RuntimeRiskClassification.HIGH
    if intent.category in {"recursive repair", "autonomous repair", "governed mutation"}:
        return RuntimeRiskClassification.MEDIUM
    return RuntimeRiskClassification.LOW


__all__ = [
    "RuntimeIntent",
    "RuntimeIntentEvaluation",
    "RuntimeIntentPolicy",
    "RuntimeRiskClassification",
    "classify_runtime_intent",
]
