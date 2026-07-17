from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Mapping

from core.runtime.runtime_capability_authorization_token import MAX_TOKEN_TTL_SECONDS
from core.runtime.runtime_capability_authorization_token_issuance_eligibility import (
    CAPABILITY_AUTHORIZATION_TOKEN_ISSUANCE_ELIGIBILITY_SCHEMA,
    TOKEN_ISSUANCE_ELIGIBILITY_STATUSES, _DOWNSTREAM_FLAGS, _FORBIDDEN_FIELDS,
    _LINEAGES, _hash,
)

@dataclass(frozen=True)
class CapabilityAuthorizationTokenIssuanceEligibilityValidationResult:
    valid: bool
    errors: tuple[str, ...]

_BASE = {
    "schema", "eligibility_id", "status", *TOKEN_ISSUANCE_ELIGIBILITY_STATUSES,
    "evaluated_at", "authorization_token_id", "authorization_token_fingerprint",
    "authorization_token_status", "token_created_at", "token_expires_at",
    "token_ttl_seconds", "authorization_token_preparation_id",
    "authorization_token_preparation_fingerprint", "authorization_token_preparation_status",
    "token_prepared_at", "authorization_token_eligibility_id",
    "authorization_token_eligibility_fingerprint", "authorization_token_eligibility_status",
    "token_eligibility_evaluated_at", "active_authorization_id",
    "active_authorization_fingerprint", "active_authorization_status", "authorized_at",
    "authorization_expires_at", "authorization_ttl_seconds",
    "issuance_eligibility_confirmed", *_DOWNSTREAM_FLAGS, "reasons", "errors", "fingerprint",
}
_REQUIRED = _BASE | {prefix + suffix for prefix in _LINEAGES for suffix in ("_id", "_fingerprint")}

def validate_capability_authorization_token_issuance_eligibility(
    value: Any,
) -> CapabilityAuthorizationTokenIssuanceEligibilityValidationResult:
    if not isinstance(value, Mapping):
        return CapabilityAuthorizationTokenIssuanceEligibilityValidationResult(False, ("eligibility_not_object",))
    errors: list[str] = []
    keys = set(value)
    if keys != _REQUIRED: errors.append("invalid_fields")
    if keys & _FORBIDDEN_FIELDS: errors.append("forged_authority_field")
    if value.get("schema") != CAPABILITY_AUTHORIZATION_TOKEN_ISSUANCE_ELIGIBILITY_SCHEMA: errors.append("invalid_schema")
    status = value.get("status")
    if status not in TOKEN_ISSUANCE_ELIGIBILITY_STATUSES: errors.append("invalid_status")
    if any(value.get(name) is not (name == status) for name in TOKEN_ISSUANCE_ELIGIBILITY_STATUSES): errors.append("inconsistent_status_flags")
    times: dict[str, datetime] = {}
    for field in ("evaluated_at", "token_created_at", "token_expires_at", "token_prepared_at", "token_eligibility_evaluated_at", "authorized_at", "authorization_expires_at"):
        try:
            parsed = datetime.fromisoformat(value.get(field, "").replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None: raise ValueError
            times[field] = parsed
        except (AttributeError, TypeError, ValueError): errors.append("invalid_" + field)
    ttl = value.get("token_ttl_seconds")
    if not isinstance(ttl, int) or isinstance(ttl, bool) or not 0 < ttl <= MAX_TOKEN_TTL_SECONDS: errors.append("invalid_token_ttl")
    if "token_created_at" in times and "token_expires_at" in times and isinstance(ttl, int) and not isinstance(ttl, bool):
        if (times["token_expires_at"] - times["token_created_at"]).total_seconds() != ttl: errors.append("token_ttl_mismatch")
    auth_ttl = value.get("authorization_ttl_seconds")
    if not isinstance(auth_ttl, int) or isinstance(auth_ttl, bool) or auth_ttl <= 0: errors.append("invalid_authorization_ttl")
    if "authorized_at" in times and "authorization_expires_at" in times and isinstance(auth_ttl, int) and not isinstance(auth_ttl, bool):
        if (times["authorization_expires_at"] - times["authorized_at"]).total_seconds() != auth_ttl: errors.append("authorization_ttl_mismatch")
    if value.get("authorization_token_status") == "created" and "token_expires_at" in times and "authorization_expires_at" in times and times["token_expires_at"] > times["authorization_expires_at"]: errors.append("token_expiry_exceeds_authorization")
    for prefix in ("authorization_token", "authorization_token_preparation", "authorization_token_eligibility", "active_authorization") + _LINEAGES:
        if not isinstance(value.get(prefix + "_id"), str) or not value.get(prefix + "_id") or not isinstance(value.get(prefix + "_fingerprint"), str) or not value.get(prefix + "_fingerprint"): errors.append("missing_linkage")
    for field in ("authorization_token_status", "authorization_token_preparation_status", "authorization_token_eligibility_status", "active_authorization_status"):
        if not isinstance(value.get(field), str) or not value.get(field): errors.append("invalid_upstream_status")
    if value.get("issuance_eligibility_confirmed") is not (status == "eligible"): errors.append("inconsistent_issuance_eligibility")
    if any(value.get(name) is not False for name in _DOWNSTREAM_FLAGS): errors.append("issuance_state_violation")
    for name in ("reasons", "errors"):
        item = value.get(name)
        if not isinstance(item, list) or item != sorted(set(item)) or any(not isinstance(code, str) or not code or len(code) > 128 or not re.fullmatch(r"[a-z0-9_]+", code) for code in item): errors.append("invalid_" + name)
    try:
        expected = _hash({key: item for key, item in value.items() if key not in {"eligibility_id", "fingerprint"}})
        if value.get("fingerprint") != expected: errors.append("fingerprint_mismatch")
        if value.get("eligibility_id") != "capability-authorization-token-issuance-eligibility-" + expected[:24]: errors.append("eligibility_id_mismatch")
    except (TypeError, ValueError): errors.append("noncanonical_value")
    return CapabilityAuthorizationTokenIssuanceEligibilityValidationResult(not errors, tuple(dict.fromkeys(errors)))

__all__ = ["CapabilityAuthorizationTokenIssuanceEligibilityValidationResult", "validate_capability_authorization_token_issuance_eligibility"]
