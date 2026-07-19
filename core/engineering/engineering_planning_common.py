from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.engineering.engineering_intake_common import canonical_json, fingerprint, identified, identity_valid
from core.engineering.repository_analysis_common import ValidationResult

FORBIDDEN_AUTHORITIES = frozenset({"execution_authority", "mutation_authority", "approval_authority", "authorization_authority", "proposal"})
ALLOWED_ACTIONS = ("analyze", "design", "document", "implement", "inspect", "validate")
FORBIDDEN_ACTIONS = ("approval granting", "authorization granting", "direct mutation without later governed authorization", "scope expansion")


def planning_boundary() -> dict[str, bool]:
    return {"sealed": True, "read_only": True, "planning_completed": False,
            "proposal_created": False, "repository_modified": False,
            "execution_started": False, "mutation_allowed": False,
            "approval_granted": False, "authorization_granted": False,
            "authority_granted": False, "scope_expansion": False}


def planning_artifact(schema: str, status: str, payload: Mapping[str, Any], id_key: str, prefix: str) -> dict[str, Any]:
    return identified({"schema": schema, "status": status, **deepcopy(dict(payload)), "boundary": planning_boundary()}, id_key, prefix)


def validate_planning_artifact(value: Any, *, schema: str, statuses: set[str], id_key: str,
                               prefix: str, fields: set[str]) -> ValidationResult:
    if not isinstance(value, Mapping):
        return ValidationResult(False, ("artifact_not_object",))
    required = {"schema", "status", id_key, "fingerprint", "boundary", *fields}
    errors = [f"missing:{key}" for key in sorted(required - set(value))]
    errors += [f"unexpected:{key}" for key in sorted(set(value) - required)]
    if value.get("schema") != schema or value.get("status") not in statuses:
        errors.append("invalid_contract")
    if value.get("boundary") != planning_boundary():
        errors.append("unsafe_boundary")
    try:
        if not identity_valid(value, id_key, prefix): errors.append("identity_mismatch")
    except (TypeError, ValueError): errors.append("identity_mismatch")
    return ValidationResult(not errors, tuple(dict.fromkeys(errors)))


def stable_id(prefix: str, value: Mapping[str, Any]) -> str:
    return prefix + fingerprint(value)[:24]


def immutable(value: Any) -> Any: return deepcopy(value)
def stable_strings(values: Any) -> list[str]:
    if not isinstance(values, list) or any(not isinstance(x, str) or not x for x in values): raise ValueError("invalid_string_list")
    return sorted(set(values))

__all__ = ["ALLOWED_ACTIONS", "FORBIDDEN_ACTIONS", "ValidationResult", "canonical_json", "fingerprint", "immutable", "planning_artifact", "planning_boundary", "stable_id", "stable_strings", "validate_planning_artifact"]
