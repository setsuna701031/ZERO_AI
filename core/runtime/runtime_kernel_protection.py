"""Protected runtime kernel zones."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.runtime.runtime_authority import RuntimeIdentity


PROTECTION_ZONE_NAMES = frozenset(
    {
        "KERNEL_CORE",
        "EXECUTION_GOVERNANCE",
        "MUTATION_GOVERNANCE",
        "REPLAY_ENGINE",
        "AUDIT_LAYER",
        "POLICY_LAYER",
    }
)

PROTECTED_PATHS = (
    "core/runtime/",
    "core/tasks/",
    "core/audit/",
)

APPROVED_GOVERNANCE_FILES = (
    "core/runtime/runtime_authority.py",
    "core/runtime/runtime_capability_scope.py",
    "core/runtime/runtime_kernel_protection.py",
    "core/runtime/runtime_execution_policy.py",
    "core/runtime/runtime_mutation_policy.py",
    "core/runtime/runtime_mutation_gateway.py",
    "core/runtime/runtime_mutation_transaction.py",
    "core/runtime/runtime_state_snapshot.py",
)


@dataclass(frozen=True)
class RuntimeProtectionZone:
    zone_id: str
    zone_name: str
    protected_paths: tuple[str, ...]
    approved_files: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeProtectionDecision:
    state: str
    reason: str
    zone: RuntimeProtectionZone | None
    identity: RuntimeIdentity
    target_path: str
    risk_level: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.state == "allowed"


@dataclass(frozen=True)
class RuntimeProtectionResult:
    decision: RuntimeProtectionDecision
    evaluated: bool = True

    @property
    def allowed(self) -> bool:
        return self.decision.allowed

    def to_metadata(self) -> dict[str, Any]:
        return {
            "protection_evaluated": self.evaluated,
            "protection_state": self.decision.state,
            "protection_reason": self.decision.reason,
            "protection_zone": (
                self.decision.zone.zone_name if self.decision.zone else None
            ),
            "protection_target_path": self.decision.target_path,
            "protection_risk_level": self.decision.risk_level,
            "protection_metadata": dict(self.decision.metadata),
        }


class RuntimeKernelProtection:
    def __init__(
        self,
        zones: tuple[RuntimeProtectionZone, ...] | None = None,
    ) -> None:
        self.zones = zones or default_protection_zones()

    def evaluate(
        self,
        *,
        identity: RuntimeIdentity,
        target_path: str | Path,
        mutation_type: str,
        risk_level: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeProtectionResult:
        metadata = dict(metadata or {})
        target_text = _normalize_path(str(target_path))
        zone = self._zone_for_path(target_text)
        identity_type = str(identity.identity_type or "").upper()

        if zone is None:
            return self._result(
                state="allowed",
                reason="target_outside_protected_zones",
                zone=None,
                identity=identity,
                target_path=target_text,
                risk_level=risk_level,
                metadata=metadata,
            )

        if _is_approved_file(target_text) and metadata.get("explicit_authority"):
            return self._result(
                state="allowed",
                reason="approved_governance_file_with_explicit_authority",
                zone=zone,
                identity=identity,
                target_path=target_text,
                risk_level=risk_level,
                metadata=metadata,
            )

        if identity_type == "SELF_EDIT":
            return self._result(
                state="blocked",
                reason="self_edit_cannot_mutate_governance_layer_by_default",
                zone=zone,
                identity=identity,
                target_path=target_text,
                risk_level=risk_level,
                metadata=metadata,
            )
        if identity_type == "REPLAY_ENGINE":
            return self._result(
                state="blocked",
                reason="replay_engine_cannot_mutate_protected_runtime_state",
                zone=zone,
                identity=identity,
                target_path=target_text,
                risk_level=risk_level,
                metadata=metadata,
            )
        if identity_type == "EXTERNAL_CONNECTOR":
            return self._result(
                state="blocked",
                reason="external_connector_cannot_mutate_kernel_paths",
                zone=zone,
                identity=identity,
                target_path=target_text,
                risk_level=risk_level,
                metadata=metadata,
            )
        if identity_type == "PERSONA":
            return self._result(
                state="blocked",
                reason="persona_cannot_mutate_runtime_governance_paths",
                zone=zone,
                identity=identity,
                target_path=target_text,
                risk_level=risk_level,
                metadata=metadata,
            )

        if risk_level in {"HIGH", "IRREVERSIBLE"} and not metadata.get("explicit_authority"):
            return self._result(
                state="blocked",
                reason="protected_zone_high_risk_requires_explicit_authority",
                zone=zone,
                identity=identity,
                target_path=target_text,
                risk_level=risk_level,
                metadata=metadata,
            )

        return self._result(
            state="allowed",
            reason="protected_zone_authority_allows_request",
            zone=zone,
            identity=identity,
            target_path=target_text,
            risk_level=risk_level,
            metadata=metadata,
        )

    def _zone_for_path(self, target_path: str) -> RuntimeProtectionZone | None:
        for zone in self.zones:
            if _path_matches_any(target_path, zone.protected_paths):
                return zone
        return None

    def _result(
        self,
        *,
        state: str,
        reason: str,
        zone: RuntimeProtectionZone | None,
        identity: RuntimeIdentity,
        target_path: str,
        risk_level: str,
        metadata: Mapping[str, Any],
    ) -> RuntimeProtectionResult:
        return RuntimeProtectionResult(
            decision=RuntimeProtectionDecision(
                state=state,
                reason=reason,
                zone=zone,
                identity=identity,
                target_path=target_path,
                risk_level=risk_level,
                metadata=dict(metadata),
            )
        )


def default_protection_zones() -> tuple[RuntimeProtectionZone, ...]:
    return (
        RuntimeProtectionZone(
            zone_id="zone:kernel_core",
            zone_name="KERNEL_CORE",
            protected_paths=PROTECTED_PATHS,
            approved_files=APPROVED_GOVERNANCE_FILES,
        ),
        RuntimeProtectionZone(
            zone_id="zone:execution_governance",
            zone_name="EXECUTION_GOVERNANCE",
            protected_paths=("core/runtime/runtime_execution_", "core/runtime/executor.py"),
            approved_files=APPROVED_GOVERNANCE_FILES,
        ),
        RuntimeProtectionZone(
            zone_id="zone:mutation_governance",
            zone_name="MUTATION_GOVERNANCE",
            protected_paths=("core/runtime/runtime_mutation_",),
            approved_files=APPROVED_GOVERNANCE_FILES,
        ),
        RuntimeProtectionZone(
            zone_id="zone:replay_engine",
            zone_name="REPLAY_ENGINE",
            protected_paths=("core/runtime/runtime_replay",),
            approved_files=APPROVED_GOVERNANCE_FILES,
        ),
        RuntimeProtectionZone(
            zone_id="zone:audit_layer",
            zone_name="AUDIT_LAYER",
            protected_paths=("core/audit/", "core/runtime/audit_"),
            approved_files=APPROVED_GOVERNANCE_FILES,
        ),
        RuntimeProtectionZone(
            zone_id="zone:policy_layer",
            zone_name="POLICY_LAYER",
            protected_paths=("core/runtime/runtime_execution_policy.py", "core/runtime/runtime_mutation_policy.py"),
            approved_files=APPROVED_GOVERNANCE_FILES,
        ),
    )


def _is_approved_file(target_path: str) -> bool:
    return any(target_path.endswith(_normalize_path(path)) for path in APPROVED_GOVERNANCE_FILES)


def _path_matches_any(path: str, patterns: Iterable[str]) -> bool:
    normalized_path = _normalize_path(path)
    for pattern in patterns:
        text = _normalize_path(str(pattern))
        if text and text in normalized_path:
            return True
    return False


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").lower()
