"""Immutable capability provenance from authority decision to persistence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping


CAPABILITY_PROPAGATION_STAGES = (
    "authority",
    "capability",
    "dispatcher",
    "runtime",
    "mutation",
    "evidence",
    "persistence",
)


class RuntimeCapabilityPropagationError(PermissionError):
    pass


@dataclass(frozen=True)
class RuntimeCapabilityProvenance:
    capability_id: str
    authority_decision_id: str
    issuer: str
    resource: str
    action: str
    execution_id: str
    scope: tuple[tuple[str, str], ...]
    lineage: tuple[tuple[str, str], ...]
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "zero.runtime.capability_provenance.v1",
            "capability_id": self.capability_id,
            "authority_decision_id": self.authority_decision_id,
            "issuer": self.issuer,
            "resource": self.resource,
            "action": self.action,
            "execution_id": self.execution_id,
            "scope": dict(self.scope),
            "lineage": dict(self.lineage),
            "fingerprint": self.fingerprint,
        }

    def __deepcopy__(self, memo: dict[int, Any]) -> "RuntimeCapabilityProvenance":
        return self


def capability_from_authority_decision(
    decision: Any,
    *,
    issuer: str,
    resource: str,
    action: str,
    scope: Mapping[str, Any],
    lineage: Mapping[str, Any],
) -> RuntimeCapabilityProvenance:
    allowed = bool(getattr(decision, "allowed", False))
    decision_id = str(getattr(decision, "decision_id", "") or "").strip()
    if not allowed or not decision_id:
        raise RuntimeCapabilityPropagationError("allowed_authority_decision_required")
    normalized_scope = _claims(scope)
    normalized_lineage = _claims(lineage)
    if not normalized_scope or not normalized_lineage:
        raise RuntimeCapabilityPropagationError("capability_scope_and_lineage_required")
    if "*" in {str(resource), str(action)} or any(value == "*" for _, value in normalized_scope):
        raise RuntimeCapabilityPropagationError("wildcard_capability_forbidden")
    scope_execution = str(scope.get("execution_id") or "").strip()
    lineage_execution = str(lineage.get("execution_id") or "").strip()
    if scope_execution and lineage_execution and scope_execution != lineage_execution:
        raise RuntimeCapabilityPropagationError("capability_execution_identity_drift")
    core = {
        "authority_decision_id": decision_id,
        "issuer": str(issuer),
        "resource": str(resource),
        "action": str(action),
        "execution_id": scope_execution or lineage_execution,
        "scope": dict(normalized_scope),
        "lineage": dict(normalized_lineage),
    }
    fingerprint = _fingerprint(core)
    return RuntimeCapabilityProvenance(
        capability_id=f"runtime-capability:{fingerprint[:24]}",
        fingerprint=fingerprint,
        scope=normalized_scope,
        lineage=normalized_lineage,
        **{key: core[key] for key in ("authority_decision_id", "issuer", "resource", "action", "execution_id")},
    )


def validate_capability_provenance(value: Any) -> RuntimeCapabilityProvenance:
    if isinstance(value, Mapping):
        try:
            value = RuntimeCapabilityProvenance(
                capability_id=str(value["capability_id"]),
                authority_decision_id=str(value["authority_decision_id"]),
                issuer=str(value["issuer"]),
                resource=str(value["resource"]),
                action=str(value["action"]),
                execution_id=str(value.get("execution_id") or ""),
                scope=_claims(value["scope"]),
                lineage=_claims(value["lineage"]),
                fingerprint=str(value["fingerprint"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeCapabilityPropagationError("invalid_capability_provenance") from exc
    if not isinstance(value, RuntimeCapabilityProvenance):
        raise RuntimeCapabilityPropagationError("live_capability_provenance_required")
    payload = value.to_dict()
    core = {key: payload[key] for key in ("authority_decision_id", "issuer", "resource", "action", "execution_id", "scope", "lineage")}
    if value.fingerprint != _fingerprint(core) or value.capability_id != f"runtime-capability:{value.fingerprint[:24]}":
        raise RuntimeCapabilityPropagationError("capability_provenance_integrity_failure")
    return value


def propagate_runtime_capability(
    metadata: Mapping[str, Any] | None,
    capability: Any,
    *,
    stage: str,
) -> dict[str, Any]:
    provenance = validate_capability_provenance(capability)
    if stage not in CAPABILITY_PROPAGATION_STAGES:
        raise RuntimeCapabilityPropagationError("unknown_capability_propagation_stage")
    payload = dict(metadata or {})
    existing_id = str(payload.get("runtime_capability_id") or "")
    existing_decision = str(payload.get("runtime_authority_decision_id") or "")
    if existing_id and existing_id != provenance.capability_id:
        raise RuntimeCapabilityPropagationError("runtime_capability_override_forbidden")
    if existing_decision and existing_decision != provenance.authority_decision_id:
        raise RuntimeCapabilityPropagationError("runtime_capability_authority_drift")
    prior_stage = str(payload.get("runtime_capability_stage") or "")
    if prior_stage and CAPABILITY_PROPAGATION_STAGES.index(prior_stage) > CAPABILITY_PROPAGATION_STAGES.index(stage):
        raise RuntimeCapabilityPropagationError("runtime_capability_stage_regression")
    return {
        **payload,
        "runtime_capability_id": provenance.capability_id,
        "runtime_authority_decision_id": provenance.authority_decision_id,
        "runtime_capability_provenance": provenance,
        "runtime_capability_stage": stage,
    }


def assert_runtime_capability_consistency(*values: Any) -> str:
    ids: set[str] = set()
    for value in values:
        if value is None:
            continue
        if isinstance(value, RuntimeCapabilityProvenance):
            ids.add(validate_capability_provenance(value).capability_id)
        elif isinstance(value, Mapping):
            capability_id = str(value.get("runtime_capability_id") or value.get("capability_id") or "")
            if capability_id:
                ids.add(capability_id)
    if len(ids) != 1:
        raise RuntimeCapabilityPropagationError("runtime_capability_consistency_failure")
    return next(iter(ids))


def _claims(values: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((str(key), str(value)) for key, value in dict(values or {}).items() if str(key) and str(value)))


def _fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "CAPABILITY_PROPAGATION_STAGES",
    "RuntimeCapabilityPropagationError",
    "RuntimeCapabilityProvenance",
    "assert_runtime_capability_consistency",
    "capability_from_authority_decision",
    "propagate_runtime_capability",
    "validate_capability_provenance",
]
