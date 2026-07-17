from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Mapping

from core.runtime.runtime_capability_active_authorization import MAX_AUTHORIZATION_TTL_SECONDS
from core.runtime.runtime_capability_authorization_token_preparation import (
    CAPABILITY_AUTHORIZATION_TOKEN_PREPARATION_SCHEMA, TOKEN_PREPARATION_STATUSES,
    _FORBIDDEN_FIELDS, _LINEAGES, _POST_PREPARATION_FLAGS, _hash,
)


@dataclass(frozen=True)
class CapabilityAuthorizationTokenPreparationValidationResult:
    valid: bool
    errors: tuple[str, ...]


_BASE = {
    "schema", "preparation_id", "status", *TOKEN_PREPARATION_STATUSES, "prepared_at",
    "authorization_token_eligibility_id", "authorization_token_eligibility_fingerprint",
    "authorization_token_eligibility_status", "active_authorization_id",
    "active_authorization_fingerprint", "active_authorization_status", "authorized_at",
    "expires_at", "authorization_ttl_seconds", "eligibility_evaluated_at",
    "token_preparation_created", *_POST_PREPARATION_FLAGS, "reasons", "errors", "fingerprint",
}
_REQUIRED = _BASE | {prefix + suffix for prefix in _LINEAGES for suffix in ("_id", "_fingerprint")}


def validate_capability_authorization_token_preparation(value: Any) -> CapabilityAuthorizationTokenPreparationValidationResult:
    if not isinstance(value, Mapping):
        return CapabilityAuthorizationTokenPreparationValidationResult(False, ("preparation_not_object",))
    errors: list[str] = []
    keys = set(value)
    if keys != _REQUIRED: errors.append("invalid_fields")
    if keys & _FORBIDDEN_FIELDS: errors.append("forged_authority_field")
    if value.get("schema") != CAPABILITY_AUTHORIZATION_TOKEN_PREPARATION_SCHEMA: errors.append("invalid_schema")
    status = value.get("status")
    if status not in TOKEN_PREPARATION_STATUSES: errors.append("invalid_status")
    if any(value.get(name) is not (name == status) for name in TOKEN_PREPARATION_STATUSES): errors.append("inconsistent_status_flags")
    parsed_times: dict[str, datetime] = {}
    for field in ("prepared_at", "eligibility_evaluated_at", "authorized_at", "expires_at"):
        try:
            parsed = datetime.fromisoformat(value.get(field, "").replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None: raise ValueError
            parsed_times[field] = parsed
        except (AttributeError, TypeError, ValueError): errors.append("invalid_" + field)
    ttl = value.get("authorization_ttl_seconds")
    if not isinstance(ttl, int) or isinstance(ttl, bool) or not 0 < ttl <= MAX_AUTHORIZATION_TTL_SECONDS: errors.append("invalid_ttl")
    if "authorized_at" in parsed_times and "expires_at" in parsed_times and isinstance(ttl, int) and not isinstance(ttl, bool):
        if (parsed_times["expires_at"] - parsed_times["authorized_at"]).total_seconds() != ttl: errors.append("ttl_mismatch")
    for prefix in ("authorization_token_eligibility", "active_authorization") + _LINEAGES:
        if not isinstance(value.get(prefix + "_id"), str) or not value.get(prefix + "_id") or not isinstance(value.get(prefix + "_fingerprint"), str) or not value.get(prefix + "_fingerprint"): errors.append("missing_linkage")
    for field in ("authorization_token_eligibility_status", "active_authorization_status"):
        if not isinstance(value.get(field), str) or not value.get(field): errors.append("invalid_upstream_status")
    if value.get("token_preparation_created") is not (status == "prepared"): errors.append("inconsistent_token_preparation")
    if any(value.get(name) is not False for name in _POST_PREPARATION_FLAGS): errors.append("token_state_violation")
    for name in ("reasons", "errors"):
        item = value.get(name)
        if not isinstance(item, list) or item != sorted(set(item)) or any(not isinstance(code, str) or not code or len(code) > 128 or not re.fullmatch(r"[a-z0-9_]+", code) for code in item): errors.append("invalid_" + name)
    try:
        expected = _hash({key: item for key, item in value.items() if key not in {"preparation_id", "fingerprint"}})
        if value.get("fingerprint") != expected: errors.append("fingerprint_mismatch")
        if value.get("preparation_id") != "capability-authorization-token-preparation-" + expected[:24]: errors.append("preparation_id_mismatch")
    except (TypeError, ValueError): errors.append("noncanonical_value")
    return CapabilityAuthorizationTokenPreparationValidationResult(not errors, tuple(dict.fromkeys(errors)))


__all__ = ["CapabilityAuthorizationTokenPreparationValidationResult", "validate_capability_authorization_token_preparation"]
