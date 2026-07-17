from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Mapping

from core.runtime.runtime_capability_active_authorization import MAX_AUTHORIZATION_TTL_SECONDS
from core.runtime.runtime_capability_authorization_token_eligibility import (
    CAPABILITY_AUTHORIZATION_TOKEN_ELIGIBILITY_SCHEMA, TOKEN_ELIGIBILITY_STATUSES,
    _DOWNSTREAM_FLAGS, _FORBIDDEN_FIELDS, _LINEAGES, _hash,
)


@dataclass(frozen=True)
class CapabilityAuthorizationTokenEligibilityValidationResult:
    valid: bool
    errors: tuple[str, ...]


_BASE = {
    "schema", "eligibility_id", "status", *TOKEN_ELIGIBILITY_STATUSES, "evaluated_at",
    "active_authorization_id", "active_authorization_fingerprint", "active_authorization_status",
    "authorized_at", "expires_at", "authorization_ttl_seconds", "token_eligibility_confirmed",
    *_DOWNSTREAM_FLAGS, "reasons", "errors", "fingerprint",
}
_REQUIRED = _BASE | {prefix + suffix for prefix in _LINEAGES for suffix in ("_id", "_fingerprint")}


def validate_capability_authorization_token_eligibility(
    value: Any,
) -> CapabilityAuthorizationTokenEligibilityValidationResult:
    if not isinstance(value, Mapping):
        return CapabilityAuthorizationTokenEligibilityValidationResult(False, ("eligibility_not_object",))
    errors: list[str] = []
    keys = set(value)
    if keys != _REQUIRED: errors.append("invalid_fields")
    if keys & _FORBIDDEN_FIELDS: errors.append("forged_authority_field")
    if value.get("schema") != CAPABILITY_AUTHORIZATION_TOKEN_ELIGIBILITY_SCHEMA: errors.append("invalid_schema")
    status = value.get("status")
    if status not in TOKEN_ELIGIBILITY_STATUSES: errors.append("invalid_status")
    if any(value.get(name) is not (name == status) for name in TOKEN_ELIGIBILITY_STATUSES): errors.append("inconsistent_status_flags")
    for field in ("evaluated_at", "authorized_at", "expires_at"):
        try:
            parsed = datetime.fromisoformat(value.get(field, "").replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None: raise ValueError
        except (AttributeError, TypeError, ValueError): errors.append("invalid_" + field)
    ttl = value.get("authorization_ttl_seconds")
    if not isinstance(ttl, int) or isinstance(ttl, bool) or not 0 < ttl <= MAX_AUTHORIZATION_TTL_SECONDS: errors.append("invalid_ttl")
    for prefix in ("active_authorization",) + _LINEAGES:
        if not isinstance(value.get(prefix + "_id"), str) or not value.get(prefix + "_id") or not isinstance(value.get(prefix + "_fingerprint"), str) or not value.get(prefix + "_fingerprint"): errors.append("missing_linkage")
    if not isinstance(value.get("active_authorization_status"), str) or not value.get("active_authorization_status"): errors.append("invalid_authorization_status")
    if value.get("token_eligibility_confirmed") is not (status == "eligible"): errors.append("inconsistent_token_eligibility")
    if any(value.get(name) is not False for name in _DOWNSTREAM_FLAGS): errors.append("token_state_violation")
    for name in ("reasons", "errors"):
        item = value.get(name)
        if not isinstance(item, list) or item != sorted(set(item)) or any(not isinstance(code, str) or not code or len(code) > 128 or not re.fullmatch(r"[a-z0-9_]+", code) for code in item): errors.append("invalid_" + name)
    try:
        expected = _hash({key: item for key, item in value.items() if key not in {"eligibility_id", "fingerprint"}})
        if value.get("fingerprint") != expected: errors.append("fingerprint_mismatch")
        if value.get("eligibility_id") != "capability-authorization-token-eligibility-" + expected[:24]: errors.append("eligibility_id_mismatch")
    except (TypeError, ValueError): errors.append("noncanonical_value")
    return CapabilityAuthorizationTokenEligibilityValidationResult(not errors, tuple(dict.fromkeys(errors)))


__all__ = ["CapabilityAuthorizationTokenEligibilityValidationResult", "validate_capability_authorization_token_eligibility"]
