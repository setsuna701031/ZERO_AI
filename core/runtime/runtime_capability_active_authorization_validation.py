from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Mapping

from core.runtime.runtime_capability_active_authorization import CAPABILITY_ACTIVE_AUTHORIZATION_SCHEMA, ACTIVE_AUTHORIZATION_STATUSES, MAX_AUTHORIZATION_TTL_SECONDS, _FORGED, _LINEAGES, _hash

@dataclass(frozen=True)
class CapabilityActiveAuthorizationValidationResult:
    valid: bool
    errors: tuple[str, ...]

_BASE = {"schema", "authorization_id", "status", *ACTIVE_AUTHORIZATION_STATUSES, "authorized_at", "expires_at", "authorization_ttl_seconds", "active_authorization_preparation_id", "active_authorization_preparation_fingerprint", "active_authorization_preparation_status", "active_authorization_created", "authorization_granted", "token_issued", "runtime_activated", "execution_authority_granted", "reasons", "errors", "fingerprint"}
_REQUIRED = _BASE | {prefix + suffix for prefix in _LINEAGES for suffix in ("_id", "_fingerprint")}

def validate_capability_active_authorization(value: Any) -> CapabilityActiveAuthorizationValidationResult:
    if not isinstance(value, Mapping): return CapabilityActiveAuthorizationValidationResult(False, ("authorization_not_object",))
    errors: list[str] = []; keys = set(value)
    if keys != _REQUIRED: errors.append("invalid_fields")
    if keys & _FORGED: errors.append("forged_authority_field")
    if value.get("schema") != CAPABILITY_ACTIVE_AUTHORIZATION_SCHEMA: errors.append("invalid_schema")
    status = value.get("status")
    if status not in ACTIVE_AUTHORIZATION_STATUSES: errors.append("invalid_status")
    if any(value.get(name) is not (name == status) for name in ACTIVE_AUTHORIZATION_STATUSES): errors.append("inconsistent_status_flags")
    authorized = expiry = None
    for field in ("authorized_at", "expires_at"):
        try:
            parsed = datetime.fromisoformat(value.get(field, "").replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None: raise ValueError
            if field == "authorized_at": authorized = parsed
            else: expiry = parsed
        except (AttributeError, TypeError, ValueError): errors.append("invalid_" + field)
    ttl = value.get("authorization_ttl_seconds")
    if not isinstance(ttl, int) or isinstance(ttl, bool) or not 0 < ttl <= MAX_AUTHORIZATION_TTL_SECONDS: errors.append("invalid_ttl")
    if authorized is not None and expiry is not None and isinstance(ttl, int) and not isinstance(ttl, bool):
        if (expiry - authorized).total_seconds() != ttl: errors.append("ttl_mismatch")
    for prefix in ("active_authorization_preparation",) + _LINEAGES:
        if not isinstance(value.get(prefix + "_id"), str) or not value.get(prefix + "_id") or not isinstance(value.get(prefix + "_fingerprint"), str) or not value.get(prefix + "_fingerprint"): errors.append("missing_linkage")
    active = status == "active"
    if value.get("active_authorization_created") is not active or value.get("authorization_granted") is not active: errors.append("inconsistent_authority_flags")
    if any(value.get(name) is not False for name in ("token_issued", "runtime_activated", "execution_authority_granted")): errors.append("authority_flag_violation")
    for name in ("reasons", "errors"):
        item = value.get(name)
        if not isinstance(item, list) or item != sorted(set(item)) or any(not isinstance(code, str) or not code or len(code) > 128 or not re.fullmatch(r"[a-z0-9_]+", code) for code in item): errors.append("invalid_" + name)
    try:
        expected = _hash({key: item for key, item in value.items() if key not in {"authorization_id", "fingerprint"}})
        if value.get("fingerprint") != expected: errors.append("fingerprint_mismatch")
        if value.get("authorization_id") != "capability-active-authorization-" + expected[:24]: errors.append("authorization_id_mismatch")
    except (TypeError, ValueError): errors.append("noncanonical_value")
    return CapabilityActiveAuthorizationValidationResult(not errors, tuple(dict.fromkeys(errors)))

__all__ = ["CapabilityActiveAuthorizationValidationResult", "validate_capability_active_authorization"]
