from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Mapping

from core.runtime.runtime_capability_active_authorization_preparation import (
    CAPABILITY_ACTIVE_AUTHORIZATION_PREPARATION_SCHEMA,
    PREPARATION_STATUSES,
    _AUTHORITY_FLAGS,
    _UPSTREAM_LINKAGES,
    _hash,
)


@dataclass(frozen=True)
class CapabilityActiveAuthorizationPreparationValidationResult:
    valid: bool
    errors: tuple[str, ...]


_BASE_FIELDS = {
    "schema", "preparation_id", "status", "prepared", "not_prepared", "blocked", "invalid",
    "prepared_at", "active_authorization_eligibility_id",
    "active_authorization_eligibility_fingerprint", "active_authorization_eligibility_status",
    *_AUTHORITY_FLAGS, "reasons", "errors", "fingerprint",
}
_REQUIRED = _BASE_FIELDS | {
    prefix + suffix for prefix in _UPSTREAM_LINKAGES for suffix in ("_id", "_fingerprint")
}
_FORGED_AUTHORITY = frozenset({
    "authorized", "activation_allowed", "may_execute", "runtime_permission",
    "authorization_issued", "activation_performed", "runtime_started",
})


def validate_capability_active_authorization_preparation(
    value: Any,
) -> CapabilityActiveAuthorizationPreparationValidationResult:
    if not isinstance(value, Mapping):
        return CapabilityActiveAuthorizationPreparationValidationResult(False, ("preparation_not_object",))
    errors: list[str] = []
    keys = set(value)
    if keys != _REQUIRED:
        errors.append("invalid_fields")
    if keys & _FORGED_AUTHORITY:
        errors.append("forged_authority_field")
    if value.get("schema") != CAPABILITY_ACTIVE_AUTHORIZATION_PREPARATION_SCHEMA:
        errors.append("invalid_schema")
    status = value.get("status")
    if status not in PREPARATION_STATUSES:
        errors.append("invalid_status")
    if any(value.get(name) is not (name == status) for name in PREPARATION_STATUSES):
        errors.append("inconsistent_status_flags")
    try:
        parsed = datetime.fromisoformat(value.get("prepared_at", "").replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        errors.append("invalid_timestamp")
    if not isinstance(value.get("active_authorization_eligibility_status"), str) or not value.get("active_authorization_eligibility_status"):
        errors.append("missing_eligibility_linkage")
    for prefix in ("active_authorization_eligibility",) + _UPSTREAM_LINKAGES:
        if (
            not isinstance(value.get(prefix + "_id"), str)
            or not value.get(prefix + "_id")
            or not isinstance(value.get(prefix + "_fingerprint"), str)
            or not value.get(prefix + "_fingerprint")
        ):
            errors.append("missing_linkage")
    if any(value.get(name) is not False for name in _AUTHORITY_FLAGS):
        errors.append("authority_flag_violation")
    for name in ("reasons", "errors"):
        item = value.get(name)
        if (
            not isinstance(item, list)
            or item != sorted(set(item))
            or any(not isinstance(code, str) or not code or len(code) > 128 or not re.fullmatch(r"[a-z0-9_]+", code) for code in item)
        ):
            errors.append("invalid_" + name)
    try:
        expected = _hash({key: item for key, item in value.items() if key not in {"preparation_id", "fingerprint"}})
        if value.get("fingerprint") != expected:
            errors.append("fingerprint_mismatch")
        if value.get("preparation_id") != "capability-active-authorization-preparation-" + expected[:24]:
            errors.append("preparation_id_mismatch")
    except (TypeError, ValueError):
        errors.append("noncanonical_value")
    return CapabilityActiveAuthorizationPreparationValidationResult(
        not errors, tuple(dict.fromkeys(errors))
    )


__all__ = [
    "CapabilityActiveAuthorizationPreparationValidationResult",
    "validate_capability_active_authorization_preparation",
]
