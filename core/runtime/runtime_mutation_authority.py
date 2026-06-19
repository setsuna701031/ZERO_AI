from __future__ import annotations

"""Canonical runtime mutation authority contract.

This module is intentionally small and inspectable.  It does not perform file
mutation itself; it issues and validates the authority envelope that every
runtime mutation surface must carry before it can request mutation from the
canonical gateway path.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

MUTATION_AUTHORITY_SCHEMA = "zero.runtime.mutation_authority.v1"
CANONICAL_MUTATION_AUTHORITY = "RuntimeMutationGateway"
CANONICAL_MUTATION_GATEWAY_MODULE = "core.runtime.runtime_mutation_gateway"

MUTATION_AUTHORITY_ROLE = "AUTHORITY"
MUTATION_REQUEST_ROLE = "REQUEST"
MUTATION_PROJECTION_ROLE = "PROJECTION"
MUTATION_PERSISTENCE_ROLE = "PERSISTENCE"

MUTATION_SURFACE_ROLES: dict[str, str] = {
    "core/runtime/runtime_mutation_gateway.py": MUTATION_AUTHORITY_ROLE,
    "core/runtime/governed_mutation_runtime.py": MUTATION_REQUEST_ROLE,
    "core/runtime/mutation_runtime_pipeline.py": MUTATION_REQUEST_ROLE,
    "core/runtime/mutation_patch_apply.py": MUTATION_PERSISTENCE_ROLE,
    "core/runtime/controlled_mutation_bridge.py": MUTATION_REQUEST_ROLE,
}

REQUEST_CLIENT_SURFACES = frozenset(
    path for path, role in MUTATION_SURFACE_ROLES.items() if role != MUTATION_AUTHORITY_ROLE
)

MUTATION_DECISION_TERMS = frozenset(
    {
        "authority_evaluator.evaluate",
        "capability_evaluator.evaluate",
        "kernel_protection.evaluate",
        "mutation_policy.evaluate",
        "classify_mutation_risk",
    }
)


class RuntimeMutationAuthorityError(PermissionError):
    pass


@dataclass(frozen=True)
class RuntimeMutationCapability:
    schema: str
    authority: str
    issuer: str
    source: str
    role: str
    request_id: str
    operation_type: str
    target_path: str
    allowed_operations: tuple[str, ...] = ("*",)
    allowed_targets: tuple[str, ...] = ("*",)
    provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "authority": self.authority,
            "issuer": self.issuer,
            "source": self.source,
            "role": self.role,
            "request_id": self.request_id,
            "operation_type": self.operation_type,
            "target_path": self.target_path,
            "allowed_operations": list(self.allowed_operations),
            "allowed_targets": list(self.allowed_targets),
            "provenance": dict(self.provenance),
            "metadata": dict(self.metadata),
        }


def classify_mutation_surface(path: str | Path) -> str:
    text = str(path).replace("\\", "/")
    for rel, role in MUTATION_SURFACE_ROLES.items():
        if text.endswith(rel) or text == rel:
            return role
    return "UNKNOWN"


def mutation_surface_inventory() -> dict[str, str]:
    return dict(MUTATION_SURFACE_ROLES)


def issue_runtime_mutation_capability(
    *,
    issuer: str,
    source: str,
    request_id: str,
    operation_type: str,
    target_path: str | Path,
    role: str = MUTATION_REQUEST_ROLE,
    allowed_operations: Iterable[str] = ("*",),
    allowed_targets: Iterable[str | Path] = ("*",),
    provenance: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> RuntimeMutationCapability:
    """Issue an inspectable mutation capability envelope.

    Only RuntimeMutationGateway is the canonical authority.  Request clients may
    carry a capability issued by the gateway path, but they do not own approval,
    risk, capability, or target decisions.
    """

    normalized_role = str(role or "").strip().upper()
    if normalized_role not in {
        MUTATION_AUTHORITY_ROLE,
        MUTATION_REQUEST_ROLE,
        MUTATION_PROJECTION_ROLE,
        MUTATION_PERSISTENCE_ROLE,
    }:
        raise RuntimeMutationAuthorityError(f"unknown_mutation_authority_role:{role}")

    return RuntimeMutationCapability(
        schema=MUTATION_AUTHORITY_SCHEMA,
        authority=CANONICAL_MUTATION_AUTHORITY,
        issuer=str(issuer or CANONICAL_MUTATION_AUTHORITY).strip() or CANONICAL_MUTATION_AUTHORITY,
        source=str(source or "").strip() or "runtime_mutation_authority",
        role=normalized_role,
        request_id=str(request_id or "").strip(),
        operation_type=str(operation_type or "").strip(),
        target_path=str(target_path or "").replace("\\", "/").strip(),
        allowed_operations=tuple(str(item or "").strip() for item in allowed_operations if str(item or "").strip()),
        allowed_targets=tuple(str(item or "").replace("\\", "/").strip() for item in allowed_targets if str(item or "").strip()),
        provenance=dict(provenance or {}),
        metadata=dict(metadata or {}),
    )


def _capability_payload(capability: Any) -> dict[str, Any]:
    if isinstance(capability, RuntimeMutationCapability):
        return capability.to_dict()
    if isinstance(capability, Mapping):
        return dict(capability)
    to_dict = getattr(capability, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return dict(payload)
    return {}


def validate_runtime_mutation_capability(
    capability: Any,
    *,
    source: str,
    operation_type: str,
    target_path: str | Path,
    role: str | None = None,
) -> dict[str, Any]:
    payload = _capability_payload(capability)
    if not payload:
        raise RuntimeMutationAuthorityError("runtime_mutation_capability_required")
    if payload.get("schema") != MUTATION_AUTHORITY_SCHEMA:
        raise RuntimeMutationAuthorityError("invalid_runtime_mutation_capability_schema")
    if payload.get("authority") != CANONICAL_MUTATION_AUTHORITY:
        raise RuntimeMutationAuthorityError("invalid_runtime_mutation_authority")

    expected_role = str(role or payload.get("role") or "").strip().upper()
    actual_role = str(payload.get("role") or "").strip().upper()
    if expected_role and actual_role != expected_role:
        raise RuntimeMutationAuthorityError("runtime_mutation_authority_role_mismatch")

    operation = str(operation_type or "").strip()
    allowed_operations = {str(item or "").strip() for item in payload.get("allowed_operations") or ()}
    if "*" not in allowed_operations and operation not in allowed_operations:
        raise RuntimeMutationAuthorityError("runtime_mutation_operation_outside_authority")

    target = str(target_path or "").replace("\\", "/").strip()
    allowed_targets = [str(item or "").replace("\\", "/").strip() for item in payload.get("allowed_targets") or ()]
    if "*" not in allowed_targets and not any(_target_matches(target, pattern) for pattern in allowed_targets):
        raise RuntimeMutationAuthorityError("runtime_mutation_target_outside_authority")

    return {
        **payload,
        "validated": True,
        "validated_source": str(source or "").strip(),
        "validated_operation_type": operation,
        "validated_target_path": target,
    }


def require_runtime_mutation_authority(
    capability: Any,
    *,
    source: str,
    operation_type: str,
    target_path: str | Path,
    role: str | None = None,
) -> dict[str, Any]:
    return validate_runtime_mutation_capability(
        capability,
        source=source,
        operation_type=operation_type,
        target_path=target_path,
        role=role,
    )


def build_mutation_authority_metadata(capability: Any, **extra: Any) -> dict[str, Any]:
    payload = _capability_payload(capability)
    return {
        "mutation_authority_schema": payload.get("schema", MUTATION_AUTHORITY_SCHEMA),
        "mutation_authority": payload.get("authority", CANONICAL_MUTATION_AUTHORITY),
        "mutation_authority_issuer": payload.get("issuer", ""),
        "mutation_authority_source": payload.get("source", ""),
        "mutation_authority_role": payload.get("role", ""),
        "mutation_authority_request_id": payload.get("request_id", ""),
        "mutation_authority_operation_type": payload.get("operation_type", ""),
        "mutation_authority_target_path": payload.get("target_path", ""),
        **dict(extra),
    }


def _target_matches(target: str, pattern: str) -> bool:
    if pattern == "*":
        return True
    normalized_target = target.lower()
    normalized_pattern = pattern.lower().rstrip("/")
    return normalized_target == normalized_pattern or normalized_target.startswith(normalized_pattern + "/")
