from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping

from core.runtime.runtime_capability_bootstrap_plan import canonical_json
from core.runtime.runtime_capability_active_authorization_preparation_validation import validate_capability_active_authorization_preparation

CAPABILITY_ACTIVE_AUTHORIZATION_SCHEMA = "zero.runtime.capability_active_authorization.v1"
ACTIVE_AUTHORIZATION_STATUSES = frozenset({"active", "not_authorized", "blocked", "invalid", "expired"})
DEFAULT_AUTHORIZATION_TTL_SECONDS = 300
MAX_AUTHORIZATION_TTL_SECONDS = 900
_LINEAGES = ("active_authorization_eligibility", "authorization_review_decision", "authorization_review_request", "review_policy", "review_handoff", "review", "review_eligibility", "activation_proposal", "capability_profile", "capability_strategy")
_FORGED = frozenset({"may_execute", "executor_allowed", "runtime_started", "activation_complete", "activation_allowed", "execution_allowed"})


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _parse_time(value: Any, *, default_now: bool = False) -> datetime | None:
    if value is None:
        if not default_now:
            return None
        parsed = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _format_time(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _safe_text(value: Any) -> str:
    return value if isinstance(value, str) and value else "unavailable"


def create_capability_active_authorization(
    active_authorization_preparation: Any, *, authorized_at: Any = None,
    expires_at: Any = None, authorization_ttl_seconds: Any = None,
) -> dict[str, Any]:
    preparation = dict(active_authorization_preparation) if isinstance(active_authorization_preparation, Mapping) else {}
    validation = validate_capability_active_authorization_preparation(preparation)
    authorized = _parse_time(authorized_at, default_now=True)
    explicit_expiry = _parse_time(expires_at) if expires_at is not None else None
    if authorization_ttl_seconds is None and explicit_expiry is not None and authorized is not None:
        derived_ttl = (explicit_expiry - authorized).total_seconds()
        ttl = int(derived_ttl) if derived_ttl.is_integer() else derived_ttl
    else:
        ttl = DEFAULT_AUTHORIZATION_TTL_SECONDS if authorization_ttl_seconds is None else authorization_ttl_seconds
    valid_ttl = isinstance(ttl, int) and not isinstance(ttl, bool) and 0 < ttl <= MAX_AUTHORIZATION_TTL_SECONDS
    errors: list[str] = []
    reasons: list[str] = []
    status = "invalid"

    authority_violation = any(
        name in preparation and preparation.get(name) is not False
        for name in ("active_authorization_created", "authorization_granted", "token_issued", "runtime_activated", "execution_authority_granted")
    ) or bool(set(preparation) & _FORGED)
    if authorized is None:
        errors.append("invalid_authorized_at")
    if expires_at is not None and explicit_expiry is None:
        errors.append("invalid_expires_at")
    if not valid_ttl:
        errors.append("invalid_ttl")

    expiry = explicit_expiry
    if authorized is not None and valid_ttl:
        calculated = authorized + timedelta(seconds=ttl)
        if expiry is None:
            expiry = calculated
        elif expiry != calculated:
            errors.append("ttl_mismatch")
            expiry = calculated
    if authorized is not None and expiry is not None and expiry <= authorized:
        errors.append("invalid_expires_at")

    if authority_violation:
        status = "blocked"; reasons.append("authority_flag_violation"); errors.append("authority_flag_violation")
    elif not validation.valid:
        reasons.append("preparation_invalid"); errors.append("invalid_preparation")
        translations = {"invalid_schema": "invalid_schema", "preparation_id_mismatch": "invalid_identity", "fingerprint_mismatch": "fingerprint_mismatch", "invalid_status": "invalid_status", "invalid_timestamp": "invalid_authorized_at", "missing_linkage": "missing_linkage", "inconsistent_status_flags": "inconsistent_flags"}
        errors.extend(translations[item] for item in validation.errors if item in translations)
    elif errors:
        status = "blocked"; reasons.append("ttl_out_of_bounds" if any(x in errors for x in ("invalid_ttl", "ttl_mismatch")) else "policy_precondition_blocked")
    elif preparation["status"] == "prepared":
        if expiry is not None and expiry <= datetime.now(timezone.utc):
            status = "expired"; reasons.append("authorization_expired")
        else:
            status = "active"; reasons.append("prepared_authorization_active")
    elif preparation["status"] == "not_prepared":
        status = "not_authorized"; reasons.append("not_prepared_not_authorized")
    elif preparation["status"] == "blocked":
        status = "blocked"; reasons.append("preparation_blocked"); errors.extend(preparation.get("errors", []))
    else:
        reasons.append("preparation_invalid"); errors.extend(preparation.get("errors", []))

    safe_authorized = authorized or datetime(1970, 1, 1, tzinfo=timezone.utc)
    safe_ttl = ttl if valid_ttl else DEFAULT_AUTHORIZATION_TTL_SECONDS
    safe_expiry = expiry or safe_authorized + timedelta(seconds=safe_ttl)
    base: dict[str, Any] = {
        "schema": CAPABILITY_ACTIVE_AUTHORIZATION_SCHEMA, "status": status,
        **{name: name == status for name in ACTIVE_AUTHORIZATION_STATUSES},
        "authorized_at": _format_time(safe_authorized), "expires_at": _format_time(safe_expiry),
        "authorization_ttl_seconds": safe_ttl,
        "active_authorization_preparation_id": _safe_text(preparation.get("preparation_id")),
        "active_authorization_preparation_fingerprint": _safe_text(preparation.get("fingerprint")),
        "active_authorization_preparation_status": _safe_text(preparation.get("status")),
        "active_authorization_created": status == "active", "authorization_granted": status == "active",
        "token_issued": False, "runtime_activated": False, "execution_authority_granted": False,
        "reasons": sorted(set(reasons)), "errors": sorted(set(errors)),
    }
    for prefix in _LINEAGES:
        base[prefix + "_id"] = _safe_text(preparation.get(prefix + "_id"))
        base[prefix + "_fingerprint"] = _safe_text(preparation.get(prefix + "_fingerprint"))
    fingerprint = _hash(base)
    base["authorization_id"] = "capability-active-authorization-" + fingerprint[:24]
    base["fingerprint"] = fingerprint
    result = json.loads(canonical_json(base))
    from core.runtime.runtime_capability_active_authorization_validation import validate_capability_active_authorization
    if not validate_capability_active_authorization(result).valid:
        raise RuntimeError("internal active authorization validation failed")
    return result


__all__ = ["CAPABILITY_ACTIVE_AUTHORIZATION_SCHEMA", "ACTIVE_AUTHORIZATION_STATUSES", "DEFAULT_AUTHORIZATION_TTL_SECONDS", "MAX_AUTHORIZATION_TTL_SECONDS", "create_capability_active_authorization"]
