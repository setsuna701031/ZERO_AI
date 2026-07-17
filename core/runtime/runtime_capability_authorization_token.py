from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping

from core.runtime.runtime_capability_bootstrap_plan import canonical_json
from core.runtime.runtime_capability_authorization_token_preparation_validation import (
    validate_capability_authorization_token_preparation,
)

CAPABILITY_AUTHORIZATION_TOKEN_SCHEMA = "zero.runtime.capability_authorization_token.v1"
CAPABILITY_AUTHORIZATION_TOKEN_STATUSES = frozenset(
    {"created", "not_created", "blocked", "invalid", "expired"}
)
DEFAULT_TOKEN_TTL_SECONDS = 120
MAX_TOKEN_TTL_SECONDS = 300
_LINEAGES = (
    "active_authorization_preparation", "active_authorization_eligibility",
    "authorization_review_decision", "authorization_review_request", "review_policy",
    "review_handoff", "review", "review_eligibility", "activation_proposal",
    "capability_profile", "capability_strategy",
)
_AUTHORITY_FLAGS = (
    "token_material_created", "token_signed", "token_issued", "token_handed_off",
    "runtime_activated", "execution_authority_granted",
)
_FORBIDDEN_FIELDS = frozenset({
    "token_value", "token_secret", "bearer_token", "bearer", "credential", "api_key",
    "session_key", "private_key", "public_key", "signature", "signed_payload", "mac",
    "nonce", "random_bytes", "may_execute", "executor_allowed", "activation_allowed",
    "execution_allowed", "runtime_started", "activation_complete",
})


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _parse_time(value: Any, *, default_now: bool = False) -> datetime | None:
    if value is None:
        parsed = datetime.now(timezone.utc) if default_now else None
    elif isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
    else:
        parsed = None
    if parsed is None or parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _format_time(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _safe_text(value: Any) -> str:
    return value if isinstance(value, str) and value else "unavailable"


def create_capability_authorization_token(
    authorization_token_preparation: Any, *, created_at: Any = None,
    expires_at: Any = None, token_ttl_seconds: Any = None,
) -> dict[str, Any]:
    preparation = dict(authorization_token_preparation) if isinstance(authorization_token_preparation, Mapping) else {}
    validation = validate_capability_authorization_token_preparation(preparation)
    created = _parse_time(created_at, default_now=True)
    explicit_expiry = _parse_time(expires_at) if expires_at is not None else None
    if token_ttl_seconds is None and explicit_expiry is not None and created is not None:
        seconds = (explicit_expiry - created).total_seconds()
        ttl = int(seconds) if seconds.is_integer() else seconds
    else:
        ttl = DEFAULT_TOKEN_TTL_SECONDS if token_ttl_seconds is None else token_ttl_seconds
    valid_ttl = isinstance(ttl, int) and not isinstance(ttl, bool) and 0 < ttl <= MAX_TOKEN_TTL_SECONDS
    reasons: list[str] = []
    errors: list[str] = []
    status = "invalid"
    if created is None: errors.append("invalid_created_at")
    if expires_at is not None and explicit_expiry is None: errors.append("invalid_expires_at")
    if not valid_ttl: errors.append("invalid_token_ttl")
    expiry = explicit_expiry
    if created is not None and valid_ttl:
        calculated = created + timedelta(seconds=ttl)
        if expiry is None: expiry = calculated
        elif expiry != calculated: errors.append("ttl_mismatch"); expiry = calculated
    if created is not None and expiry is not None and expiry <= created:
        errors.append("invalid_expires_at")

    authority_violation = any(
        name in preparation and preparation.get(name) is not False
        for name in ("token_created", "token_material_created", "token_signed", "token_issued", "runtime_activated", "execution_authority_granted")
    ) or bool(set(preparation) & _FORBIDDEN_FIELDS)
    if authority_violation:
        status = "blocked"; reasons.append("authority_flag_violation"); errors.append("token_state_violation")
    elif not validation.valid:
        reasons.append("token_preparation_invalid"); errors.append("invalid_token_preparation")
        translations = {
            "invalid_schema": "invalid_schema", "preparation_id_mismatch": "invalid_identity",
            "fingerprint_mismatch": "fingerprint_mismatch", "invalid_status": "invalid_status",
            "invalid_prepared_at": "invalid_created_at", "missing_linkage": "missing_linkage",
            "inconsistent_status_flags": "inconsistent_flags", "token_state_violation": "token_state_violation",
        }
        errors.extend(translations[e] for e in validation.errors if e in translations)
    elif errors:
        status = "blocked"; reasons.append("policy_precondition_blocked")
    else:
        authorized = _parse_time(preparation.get("authorized_at"))
        authorization_expiry = _parse_time(preparation.get("expires_at"))
        upstream = preparation["status"]
        if upstream == "not_prepared": status = "not_created"; reasons.append("token_not_prepared_not_created")
        elif upstream == "blocked": status = "blocked"; reasons.append("token_preparation_blocked")
        elif upstream == "invalid": status = "invalid"; reasons.append("token_preparation_invalid")
        elif upstream == "expired": status = "expired"; reasons.append("token_preparation_expired")
        elif authorized is None: status = "invalid"; reasons.append("token_preparation_invalid"); errors.append("invalid_authorized_at")
        elif authorization_expiry is None: status = "invalid"; reasons.append("token_preparation_invalid"); errors.append("invalid_authorization_expiry")
        elif created < authorized: status = "blocked"; reasons.append("authorization_not_yet_effective")
        elif created >= authorization_expiry: status = "expired"; reasons.append("authorization_expired_before_token_creation")
        elif expiry is not None and expiry > authorization_expiry:
            if expires_at is None and token_ttl_seconds is None:
                expiry = authorization_expiry
                ttl = int((expiry - created).total_seconds())
                reasons.append("token_ttl_bounded_to_authorization")
                if ttl <= 0: status = "expired"; reasons.append("authorization_expired_before_token_creation")
                else: status = "created"; reasons.append("token_preparation_token_created")
            else:
                status = "blocked"; reasons.append("policy_precondition_blocked"); errors.append("token_expiry_exceeds_authorization")
                expiry = authorization_expiry
                ttl = int((expiry - created).total_seconds())
        else: status = "created"; reasons.append("token_preparation_token_created")

    safe_created = created or datetime(1970, 1, 1, tzinfo=timezone.utc)
    safe_ttl = ttl if valid_ttl and isinstance(ttl, int) and ttl > 0 else DEFAULT_TOKEN_TTL_SECONDS
    safe_expiry = expiry or safe_created + timedelta(seconds=safe_ttl)
    if safe_expiry <= safe_created:
        safe_ttl = 1
        safe_expiry = safe_created + timedelta(seconds=1)
    else:
        safe_ttl = int((safe_expiry - safe_created).total_seconds())
    upstream_authorized = _parse_time(preparation.get("authorized_at")) or safe_created
    upstream_expiry = _parse_time(preparation.get("expires_at")) or safe_expiry
    upstream_ttl = int((upstream_expiry - upstream_authorized).total_seconds())
    if upstream_ttl <= 0:
        upstream_authorized, upstream_expiry, upstream_ttl = safe_created, safe_expiry, safe_ttl
    base: dict[str, Any] = {
        "schema": CAPABILITY_AUTHORIZATION_TOKEN_SCHEMA, "status": status,
        **{name: name == status for name in CAPABILITY_AUTHORIZATION_TOKEN_STATUSES},
        "created_at": _format_time(safe_created), "expires_at": _format_time(safe_expiry),
        "token_ttl_seconds": safe_ttl,
        "authorization_token_preparation_id": _safe_text(preparation.get("preparation_id")),
        "authorization_token_preparation_fingerprint": _safe_text(preparation.get("fingerprint")),
        "authorization_token_preparation_status": _safe_text(preparation.get("status")),
        "token_prepared_at": _format_time(_parse_time(preparation.get("prepared_at")) or safe_created),
        "authorization_token_eligibility_id": _safe_text(preparation.get("authorization_token_eligibility_id")),
        "authorization_token_eligibility_fingerprint": _safe_text(preparation.get("authorization_token_eligibility_fingerprint")),
        "authorization_token_eligibility_status": _safe_text(preparation.get("authorization_token_eligibility_status")),
        "token_eligibility_evaluated_at": _format_time(_parse_time(preparation.get("eligibility_evaluated_at")) or safe_created),
        "active_authorization_id": _safe_text(preparation.get("active_authorization_id")),
        "active_authorization_fingerprint": _safe_text(preparation.get("active_authorization_fingerprint")),
        "active_authorization_status": _safe_text(preparation.get("active_authorization_status")),
        "authorized_at": _format_time(upstream_authorized),
        "authorization_expires_at": _format_time(upstream_expiry),
        "authorization_ttl_seconds": upstream_ttl,
        "token_created": status == "created", **{name: False for name in _AUTHORITY_FLAGS},
        "reasons": sorted(set(reasons)), "errors": sorted(set(errors)),
    }
    for prefix in _LINEAGES:
        base[prefix + "_id"] = _safe_text(preparation.get(prefix + "_id"))
        base[prefix + "_fingerprint"] = _safe_text(preparation.get(prefix + "_fingerprint"))
    fingerprint = _hash(base)
    base["token_id"] = "capability-authorization-token-" + fingerprint[:24]
    base["fingerprint"] = fingerprint
    result = json.loads(canonical_json(base))
    from core.runtime.runtime_capability_authorization_token_validation import validate_capability_authorization_token
    if not validate_capability_authorization_token(result).valid:
        raise RuntimeError("internal authorization token validation failed")
    return result


__all__ = ["CAPABILITY_AUTHORIZATION_TOKEN_SCHEMA", "CAPABILITY_AUTHORIZATION_TOKEN_STATUSES", "DEFAULT_TOKEN_TTL_SECONDS", "MAX_TOKEN_TTL_SECONDS", "create_capability_authorization_token"]
