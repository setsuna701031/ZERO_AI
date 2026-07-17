from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Mapping

from core.runtime.runtime_capability_authorization_token import (
    CAPABILITY_AUTHORIZATION_TOKEN_SCHEMA, CAPABILITY_AUTHORIZATION_TOKEN_STATUSES,
    MAX_TOKEN_TTL_SECONDS, _AUTHORITY_FLAGS, _FORBIDDEN_FIELDS, _LINEAGES, _hash,
)

@dataclass(frozen=True)
class CapabilityAuthorizationTokenValidationResult:
    valid: bool
    errors: tuple[str, ...]

_BASE = {
    "schema", "token_id", "status", *CAPABILITY_AUTHORIZATION_TOKEN_STATUSES,
    "created_at", "expires_at", "token_ttl_seconds", "authorization_token_preparation_id",
    "authorization_token_preparation_fingerprint", "authorization_token_preparation_status",
    "token_prepared_at", "authorization_token_eligibility_id", "authorization_token_eligibility_fingerprint",
    "authorization_token_eligibility_status", "token_eligibility_evaluated_at", "active_authorization_id",
    "active_authorization_fingerprint", "active_authorization_status", "authorized_at",
    "authorization_expires_at", "authorization_ttl_seconds", "token_created", *_AUTHORITY_FLAGS,
    "reasons", "errors", "fingerprint",
}
_REQUIRED = _BASE | {p + s for p in _LINEAGES for s in ("_id", "_fingerprint")}

def validate_capability_authorization_token(value: Any) -> CapabilityAuthorizationTokenValidationResult:
    if not isinstance(value, Mapping):
        return CapabilityAuthorizationTokenValidationResult(False, ("token_not_object",))
    errors: list[str] = []
    keys = set(value)
    if keys != _REQUIRED: errors.append("invalid_fields")
    if keys & _FORBIDDEN_FIELDS: errors.append("forged_authority_field")
    if value.get("schema") != CAPABILITY_AUTHORIZATION_TOKEN_SCHEMA: errors.append("invalid_schema")
    status = value.get("status")
    if status not in CAPABILITY_AUTHORIZATION_TOKEN_STATUSES: errors.append("invalid_status")
    if any(value.get(s) is not (s == status) for s in CAPABILITY_AUTHORIZATION_TOKEN_STATUSES): errors.append("inconsistent_status_flags")
    times: dict[str, datetime] = {}
    for field in ("created_at", "expires_at", "token_prepared_at", "token_eligibility_evaluated_at", "authorized_at", "authorization_expires_at"):
        try:
            parsed = datetime.fromisoformat(value.get(field, "").replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None: raise ValueError
            times[field] = parsed
        except (AttributeError, TypeError, ValueError): errors.append("invalid_" + field)
    ttl = value.get("token_ttl_seconds")
    if not isinstance(ttl, int) or isinstance(ttl, bool) or not 0 < ttl <= MAX_TOKEN_TTL_SECONDS: errors.append("invalid_token_ttl")
    if "created_at" in times and "expires_at" in times and isinstance(ttl, int) and not isinstance(ttl, bool):
        if (times["expires_at"] - times["created_at"]).total_seconds() != ttl: errors.append("ttl_mismatch")
    auth_ttl = value.get("authorization_ttl_seconds")
    if not isinstance(auth_ttl, int) or isinstance(auth_ttl, bool) or auth_ttl <= 0: errors.append("invalid_authorization_ttl")
    if "authorized_at" in times and "authorization_expires_at" in times and isinstance(auth_ttl, int) and not isinstance(auth_ttl, bool):
        if (times["authorization_expires_at"] - times["authorized_at"]).total_seconds() != auth_ttl: errors.append("authorization_ttl_mismatch")
    if status == "created" and "expires_at" in times and "authorization_expires_at" in times and times["expires_at"] > times["authorization_expires_at"]: errors.append("token_expiry_exceeds_authorization")
    for prefix in ("authorization_token_preparation", "authorization_token_eligibility", "active_authorization") + _LINEAGES:
        if not isinstance(value.get(prefix + "_id"), str) or not value.get(prefix + "_id") or not isinstance(value.get(prefix + "_fingerprint"), str) or not value.get(prefix + "_fingerprint"): errors.append("missing_linkage")
    for field in ("authorization_token_preparation_status", "authorization_token_eligibility_status", "active_authorization_status"):
        if not isinstance(value.get(field), str) or not value.get(field): errors.append("invalid_upstream_status")
    if value.get("token_created") is not (status == "created"): errors.append("inconsistent_token_created")
    if any(value.get(name) is not False for name in _AUTHORITY_FLAGS): errors.append("token_state_violation")
    for name in ("reasons", "errors"):
        item = value.get(name)
        if not isinstance(item, list) or item != sorted(set(item)) or any(not isinstance(code, str) or not code or len(code) > 128 or not re.fullmatch(r"[a-z0-9_]+", code) for code in item): errors.append("invalid_" + name)
    try:
        expected = _hash({k: v for k, v in value.items() if k not in {"token_id", "fingerprint"}})
        if value.get("fingerprint") != expected: errors.append("fingerprint_mismatch")
        if value.get("token_id") != "capability-authorization-token-" + expected[:24]: errors.append("token_id_mismatch")
    except (TypeError, ValueError): errors.append("noncanonical_value")
    return CapabilityAuthorizationTokenValidationResult(not errors, tuple(dict.fromkeys(errors)))

__all__ = ["CapabilityAuthorizationTokenValidationResult", "validate_capability_authorization_token"]
