from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


def _get_attr_or_key(source: Any, name: str, default: Any = None) -> Any:
    if source is None:
        return default

    if isinstance(source, Mapping):
        return source.get(name, default)

    return getattr(source, name, default)


def _as_string_set(value: Any) -> set[str]:
    if value is None:
        return set()

    if isinstance(value, str):
        return {value}

    if isinstance(value, Mapping):
        return {str(key) for key in value.keys()}

    try:
        return {str(item) for item in value}
    except TypeError:
        return {str(value)}


def _first_present(source: Any, names: Iterable[str], default: Any = None) -> Any:
    for name in names:
        value = _get_attr_or_key(source, name, None)
        if value is not None:
            return value
    return default


@dataclass(frozen=True)
class RuntimeLegalityDecision:
    allowed: bool
    requires_review: bool
    blocked: bool
    reason: str
    violated_rules: list[str] = field(default_factory=list)
    action_type: str = ""
    risk_level: str = "unknown"
    governance_id: str | None = None
    constitution_version: str = "unknown"

    @property
    def decision(self) -> str:
        if self.blocked:
            return "BLOCK"
        if self.requires_review:
            return "REVIEW"
        if self.allowed:
            return "ALLOW"
        return "UNKNOWN"

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "requires_review": self.requires_review,
            "blocked": self.blocked,
            "decision": self.decision,
            "reason": self.reason,
            "violated_rules": list(self.violated_rules),
            "action_type": self.action_type,
            "risk_level": self.risk_level,
            "governance_id": self.governance_id,
            "constitution_version": self.constitution_version,
        }


class RuntimeLegalityEngine:
    def evaluate_action(
        self,
        action_type: str,
        risk_level: str = "unknown",
        governance_snapshot: Any = None,
        constitution: Any = None,
    ) -> RuntimeLegalityDecision:
        normalized_action = str(action_type or "").strip()
        normalized_risk = str(risk_level or "unknown").strip() or "unknown"

        governance_id = _first_present(
            governance_snapshot,
            (
                "governance_id",
                "snapshot_id",
                "ledger_id",
                "id",
            ),
            None,
        )

        constitution_version = str(
            _first_present(
                constitution,
                (
                    "constitution_version",
                    "version",
                    "runtime_constitution_version",
                ),
                "unknown",
            )
        )

        allowed_actions = _as_string_set(
            _first_present(
                constitution,
                (
                    "allowed_actions",
                    "allow_actions",
                    "allowlist",
                    "allowed_action_types",
                ),
                set(),
            )
        )
        review_required_actions = _as_string_set(
            _first_present(
                constitution,
                (
                    "review_required_actions",
                    "requires_review_actions",
                    "review_actions",
                    "review_required_action_types",
                ),
                set(),
            )
        )
        blocked_actions = _as_string_set(
            _first_present(
                constitution,
                (
                    "blocked_actions",
                    "block_actions",
                    "deny_actions",
                    "blocked_action_types",
                ),
                set(),
            )
        )

        if not normalized_action:
            return RuntimeLegalityDecision(
                allowed=False,
                requires_review=False,
                blocked=True,
                reason="Missing runtime action type.",
                violated_rules=["runtime.action_type.required"],
                action_type=normalized_action,
                risk_level=normalized_risk,
                governance_id=governance_id,
                constitution_version=constitution_version,
            )

        if normalized_action in blocked_actions:
            return RuntimeLegalityDecision(
                allowed=False,
                requires_review=False,
                blocked=True,
                reason=f"Action '{normalized_action}' is blocked by runtime constitution.",
                violated_rules=[f"runtime.action.blocked:{normalized_action}"],
                action_type=normalized_action,
                risk_level=normalized_risk,
                governance_id=governance_id,
                constitution_version=constitution_version,
            )

        if normalized_action in review_required_actions:
            return RuntimeLegalityDecision(
                allowed=False,
                requires_review=True,
                blocked=False,
                reason=f"Action '{normalized_action}' requires review by runtime constitution.",
                violated_rules=[],
                action_type=normalized_action,
                risk_level=normalized_risk,
                governance_id=governance_id,
                constitution_version=constitution_version,
            )

        if normalized_action in allowed_actions:
            return RuntimeLegalityDecision(
                allowed=True,
                requires_review=False,
                blocked=False,
                reason=f"Action '{normalized_action}' is allowed by runtime constitution.",
                violated_rules=[],
                action_type=normalized_action,
                risk_level=normalized_risk,
                governance_id=governance_id,
                constitution_version=constitution_version,
            )

        return RuntimeLegalityDecision(
            allowed=False,
            requires_review=True,
            blocked=False,
            reason=f"Action '{normalized_action}' is not explicitly allowed; review is required.",
            violated_rules=["runtime.action.not_explicitly_allowed"],
            action_type=normalized_action,
            risk_level=normalized_risk,
            governance_id=governance_id,
            constitution_version=constitution_version,
        )


def evaluate_runtime_legality(
    action_type: str,
    risk_level: str = "unknown",
    governance_snapshot: Any = None,
    constitution: Any = None,
) -> RuntimeLegalityDecision:
    return RuntimeLegalityEngine().evaluate_action(
        action_type=action_type,
        risk_level=risk_level,
        governance_snapshot=governance_snapshot,
        constitution=constitution,
    )
