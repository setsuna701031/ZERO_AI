"""Governed runtime capability scope boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.runtime.runtime_authority import RISK_ORDER


@dataclass(frozen=True)
class RuntimeCapabilityScope:
    capability_id: str
    accessible_paths: tuple[str, ...] = ()
    blocked_paths: tuple[str, ...] = ()
    allowed_mutation_types: tuple[str, ...] = ()
    allowed_execution_types: tuple[str, ...] = ()
    risk_ceiling: str = "LOW"
    sandbox_required: bool = False
    replay_allowed: bool = False
    rollback_allowed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeCapabilityPermission:
    permission_id: str
    allowed: bool
    reason: str
    capability_id: str
    target_path: str | None
    risk_level: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeCapabilityResult:
    permission: RuntimeCapabilityPermission
    evaluated: bool = True

    @property
    def allowed(self) -> bool:
        return self.permission.allowed

    def to_metadata(self) -> dict[str, Any]:
        return {
            "capability_evaluated": self.evaluated,
            "capability_allowed": self.permission.allowed,
            "capability_reason": self.permission.reason,
            "capability_id": self.permission.capability_id,
            "capability_target_path": self.permission.target_path,
            "capability_risk_level": self.permission.risk_level,
            "capability_metadata": dict(self.permission.metadata),
        }


class RuntimeCapabilityScopeEvaluator:
    def evaluate(
        self,
        *,
        capability_scope: RuntimeCapabilityScope,
        execution_type: str | None = None,
        mutation_type: str | None = None,
        target_path: str | Path | None = None,
        risk_level: str = "LOW",
        requires_replay: bool = False,
        requires_rollback: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeCapabilityResult:
        target_text = str(target_path) if target_path is not None else None
        reason = "capability_scope_allows_request"
        allowed = True

        if mutation_type and not _contains_or_wildcard(
            capability_scope.allowed_mutation_types,
            mutation_type,
        ):
            allowed = False
            reason = "mutation_type_outside_capability_scope"
        elif execution_type and not _contains_or_wildcard(
            capability_scope.allowed_execution_types,
            execution_type,
        ):
            allowed = False
            reason = "execution_type_outside_capability_scope"
        elif target_text and _path_matches_any(target_text, capability_scope.blocked_paths):
            allowed = False
            reason = "target_path_blocked_by_capability_scope"
        elif target_text and capability_scope.accessible_paths and not _path_matches_any(
            target_text,
            capability_scope.accessible_paths,
        ):
            allowed = False
            reason = "target_path_outside_capability_scope"
        elif _risk_value(risk_level) > _risk_value(capability_scope.risk_ceiling):
            allowed = False
            reason = "risk_exceeds_capability_ceiling"
        elif requires_replay and not capability_scope.replay_allowed:
            allowed = False
            reason = "replay_not_allowed_by_capability_scope"
        elif requires_rollback and not capability_scope.rollback_allowed:
            allowed = False
            reason = "rollback_not_allowed_by_capability_scope"

        return RuntimeCapabilityResult(
            permission=RuntimeCapabilityPermission(
                permission_id=f"capability_permission:{capability_scope.capability_id}",
                allowed=allowed,
                reason=reason,
                capability_id=capability_scope.capability_id,
                target_path=target_text,
                risk_level=risk_level,
                metadata={
                    **dict(metadata or {}),
                    "sandbox_required": capability_scope.sandbox_required,
                    "replay_allowed": capability_scope.replay_allowed,
                    "rollback_allowed": capability_scope.rollback_allowed,
                },
            )
        )


def default_workspace_capability_scope() -> RuntimeCapabilityScope:
    return RuntimeCapabilityScope(
        capability_id="capability:workspace:governed_mutation",
        accessible_paths=("*",),
        blocked_paths=(),
        allowed_mutation_types=("*",),
        allowed_execution_types=("*",),
        risk_ceiling="IRREVERSIBLE",
        replay_allowed=True,
        rollback_allowed=True,
    )


def _contains_or_wildcard(values: Iterable[str], item: str) -> bool:
    normalized = {str(value).strip().lower() for value in values}
    return "*" in normalized or str(item).strip().lower() in normalized


def _path_matches_any(path: str, patterns: Iterable[str]) -> bool:
    normalized_path = path.replace("\\", "/").lower()
    for pattern in patterns:
        text = str(pattern).replace("\\", "/").lower()
        if text == "*":
            return True
        if text and text in normalized_path:
            return True
    return False


def _risk_value(risk_level: str) -> int:
    return RISK_ORDER.get(str(risk_level or "LOW").upper(), RISK_ORDER["HIGH"])
