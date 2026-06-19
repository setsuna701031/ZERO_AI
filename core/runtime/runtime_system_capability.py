"""Explicit, lineage-bound capabilities for SYSTEM runtime work.

SYSTEM is an identity used by boot and infrastructure code.  It is not an
authority.  A SYSTEM operation is legal only when it carries one of the live,
scoped tokens issued and validated by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4


SYSTEM_CAPABILITY_SCHEMA = "zero.runtime.system_capability.v1"


class RuntimeCapabilityClass(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    MUTATE = "MUTATE"
    EXECUTE = "EXECUTE"
    ROLLBACK = "ROLLBACK"
    RECOVERY = "RECOVERY"
    ADMIN = "ADMIN"


SYSTEM_CAPABILITY_INVENTORY: dict[RuntimeCapabilityClass, frozenset[tuple[str, str]]] = {
    RuntimeCapabilityClass.READ: frozenset(
        {
            ("queue_state", "read"),
            ("execution_result", "read"),
            ("runtime_event", "read"),
            ("runtime_incident", "read"),
            ("runtime_snapshot", "read"),
            ("orchestration_state", "read"),
            ("repair_state", "read"),
        }
    ),
    RuntimeCapabilityClass.WRITE: frozenset(
        {
            ("runtime_event", "emit"),
            ("runtime_incident", "emit"),
            ("runtime_snapshot", "snapshot"),
        }
    ),
    RuntimeCapabilityClass.MUTATE: frozenset({("workspace", "file_write"), ("workspace", "generated_artifact_write")}),
    RuntimeCapabilityClass.EXECUTE: frozenset({("runtime_task", "execute"), ("work_package", "dispatch")}),
    RuntimeCapabilityClass.ROLLBACK: frozenset({("workspace", "rollback")}),
    RuntimeCapabilityClass.RECOVERY: frozenset({("runtime_task", "recover")}),
    RuntimeCapabilityClass.ADMIN: frozenset(),
}

SYSTEM_CAPABILITY_ISSUERS: dict[str, frozenset[RuntimeCapabilityClass]] = {
    "RuntimeDispatcher": frozenset({RuntimeCapabilityClass.EXECUTE}),
    "TaskRunner": frozenset({RuntimeCapabilityClass.EXECUTE, RuntimeCapabilityClass.ROLLBACK, RuntimeCapabilityClass.RECOVERY}),
    "TaskRuntime": frozenset({RuntimeCapabilityClass.WRITE, RuntimeCapabilityClass.ROLLBACK, RuntimeCapabilityClass.RECOVERY}),
    "RuntimeMutationGateway": frozenset({RuntimeCapabilityClass.MUTATE, RuntimeCapabilityClass.ROLLBACK}),
}


class RuntimeSystemCapabilityError(PermissionError):
    pass


@dataclass(frozen=True)
class RuntimeSystemCapabilityToken:
    token_id: str
    issuer: str
    capability_class: RuntimeCapabilityClass
    resource: str
    action: str
    scope: dict[str, str]
    lineage: dict[str, str]
    schema: str = SYSTEM_CAPABILITY_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "token_id": self.token_id,
            "issuer": self.issuer,
            "capability_class": self.capability_class.value,
            "resource": self.resource,
            "action": self.action,
            "scope": dict(self.scope),
            "lineage": dict(self.lineage),
            "authoritative": False,
        }

    def __deepcopy__(self, memo: dict[int, Any]) -> "RuntimeSystemCapabilityToken":
        return self


_LIVE_TOKENS: dict[str, RuntimeSystemCapabilityToken] = {}


def issue_runtime_system_capability(
    *,
    issuer: str,
    capability_class: RuntimeCapabilityClass | str,
    resource: str,
    action: str,
    scope: Mapping[str, Any],
    lineage: Mapping[str, Any],
) -> RuntimeSystemCapabilityToken:
    normalized_class = RuntimeCapabilityClass(str(getattr(capability_class, "value", capability_class)).upper())
    normalized_issuer = str(issuer or "").strip()
    if normalized_class not in SYSTEM_CAPABILITY_ISSUERS.get(normalized_issuer, frozenset()):
        raise RuntimeSystemCapabilityError("system_capability_issuer_not_authorized")
    normalized_scope = _normalize_claims(scope)
    normalized_lineage = _normalize_claims(lineage)
    if not normalized_scope:
        raise RuntimeSystemCapabilityError("system_capability_scope_required")
    if not normalized_lineage:
        raise RuntimeSystemCapabilityError("system_capability_lineage_required")
    normalized_resource = str(resource or "").strip()
    normalized_action = str(action or "").strip()
    if not normalized_resource or not normalized_action or "*" in {normalized_resource, normalized_action}:
        raise RuntimeSystemCapabilityError("system_capability_resource_action_must_be_explicit")
    if (normalized_resource, normalized_action) not in SYSTEM_CAPABILITY_INVENTORY[normalized_class]:
        raise RuntimeSystemCapabilityError("system_capability_not_in_explicit_inventory")
    token = RuntimeSystemCapabilityToken(
        token_id=f"system-capability:{uuid4().hex}",
        issuer=normalized_issuer,
        capability_class=normalized_class,
        resource=normalized_resource,
        action=normalized_action,
        scope=normalized_scope,
        lineage=normalized_lineage,
    )
    _LIVE_TOKENS[token.token_id] = token
    return token


def validate_runtime_system_capability(
    token: Any,
    *,
    issuer: str,
    resource: str,
    action: str,
    scope: Mapping[str, Any],
    lineage: Mapping[str, Any],
    capability_class: RuntimeCapabilityClass | str | None = None,
) -> RuntimeSystemCapabilityToken:
    if not isinstance(token, RuntimeSystemCapabilityToken) or _LIVE_TOKENS.get(token.token_id) is not token:
        raise RuntimeSystemCapabilityError("live_system_capability_required")
    if token.schema != SYSTEM_CAPABILITY_SCHEMA or token.issuer != str(issuer or "").strip():
        raise RuntimeSystemCapabilityError("system_capability_issuer_mismatch")
    if capability_class is not None:
        expected_class = RuntimeCapabilityClass(str(getattr(capability_class, "value", capability_class)).upper())
        if token.capability_class is not expected_class:
            raise RuntimeSystemCapabilityError("system_capability_class_mismatch")
    if token.resource != str(resource or "").strip() or token.action != str(action or "").strip():
        raise RuntimeSystemCapabilityError("system_capability_resource_action_mismatch")
    if not _claims_contain(token.scope, _normalize_claims(scope)):
        raise RuntimeSystemCapabilityError("system_capability_scope_mismatch")
    if not _claims_contain(token.lineage, _normalize_claims(lineage)):
        raise RuntimeSystemCapabilityError("system_capability_lineage_mismatch")
    return token


def _normalize_claims(values: Mapping[str, Any]) -> dict[str, str]:
    return {str(key): str(value) for key, value in dict(values or {}).items() if str(key) and str(value)}


def _claims_contain(granted: Mapping[str, str], requested: Mapping[str, str]) -> bool:
    return bool(requested) and all(granted.get(key) == value for key, value in requested.items())


__all__ = [
    "RuntimeCapabilityClass",
    "RuntimeSystemCapabilityError",
    "RuntimeSystemCapabilityToken",
    "SYSTEM_CAPABILITY_INVENTORY",
    "SYSTEM_CAPABILITY_ISSUERS",
    "issue_runtime_system_capability",
    "validate_runtime_system_capability",
]
