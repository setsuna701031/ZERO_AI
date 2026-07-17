from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping

from core.runtime.runtime_capability_bootstrap_plan import canonical_json
from core.runtime.runtime_capability_active_authorization import MAX_AUTHORIZATION_TTL_SECONDS
from core.runtime.runtime_capability_authorization_token_eligibility_validation import (
    validate_capability_authorization_token_eligibility,
)

CAPABILITY_AUTHORIZATION_TOKEN_PREPARATION_SCHEMA = (
    "zero.runtime.capability_authorization_token_preparation.v1"
)
TOKEN_PREPARATION_STATUSES = frozenset(
    {"prepared", "not_prepared", "blocked", "invalid", "expired"}
)
_LINEAGES = (
    "active_authorization_preparation", "active_authorization_eligibility",
    "authorization_review_decision", "authorization_review_request", "review_policy",
    "review_handoff", "review", "review_eligibility", "activation_proposal",
    "capability_profile", "capability_strategy",
)
_POST_PREPARATION_FLAGS = (
    "token_created", "token_issued", "token_signed", "token_material_created",
    "runtime_activated", "execution_authority_granted",
)
_FORBIDDEN_FIELDS = frozenset({
    "token_value", "token_secret", "signature", "private_key", "public_key",
    "bearer", "credential", "nonce", "random_bytes", "may_execute",
    "executor_allowed", "activation_allowed", "execution_allowed", "runtime_started",
})


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _timestamp(value: Any, *, default_now: bool = False) -> tuple[str | None, datetime | None]:
    if value is None:
        if not default_now:
            return None, None
        parsed = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None, None
    else:
        return None, None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, None
    parsed = parsed.astimezone(timezone.utc)
    return parsed.isoformat().replace("+00:00", "Z"), parsed


def _safe_text(value: Any) -> str:
    return value if isinstance(value, str) and value else "unavailable"


def prepare_capability_authorization_token(
    authorization_token_eligibility: Any, *, prepared_at: Any = None,
) -> dict[str, Any]:
    eligibility = dict(authorization_token_eligibility) if isinstance(authorization_token_eligibility, Mapping) else {}
    prepared_text, prepared_time = _timestamp(prepared_at, default_now=True)
    validation = validate_capability_authorization_token_eligibility(eligibility)
    reasons: list[str] = []
    errors: list[str] = []
    status = "invalid"
    authority_violation = any(
        name in eligibility and eligibility.get(name) is not False
        for name in ("token_preparation_created", "token_created", "token_issued", "token_signed", "runtime_activated", "execution_authority_granted")
    ) or bool(set(eligibility) & _FORBIDDEN_FIELDS)

    if prepared_text is None or prepared_time is None:
        reasons.append("token_eligibility_invalid"); errors.append("invalid_prepared_at")
    elif authority_violation:
        status = "blocked"; reasons.append("authority_flag_violation"); errors.append("token_state_violation")
    elif not validation.valid:
        reasons.append("token_eligibility_invalid"); errors.append("invalid_token_eligibility")
        translations = {
            "invalid_schema": "invalid_schema", "eligibility_id_mismatch": "invalid_identity",
            "fingerprint_mismatch": "fingerprint_mismatch", "invalid_status": "invalid_status",
            "invalid_evaluated_at": "invalid_evaluated_at", "invalid_authorized_at": "invalid_authorized_at",
            "invalid_expires_at": "invalid_expires_at", "invalid_ttl": "invalid_ttl",
            "missing_linkage": "missing_linkage", "inconsistent_status_flags": "inconsistent_flags",
            "inconsistent_token_eligibility": "inconsistent_flags",
        }
        errors.extend(translations[item] for item in validation.errors if item in translations)
    else:
        _, authorized = _timestamp(eligibility["authorized_at"])
        _, expires = _timestamp(eligibility["expires_at"])
        _, evaluated = _timestamp(eligibility["evaluated_at"])
        upstream_status = eligibility["status"]
        if upstream_status == "expired":
            status = "expired"; reasons.append("token_eligibility_expired")
        elif upstream_status == "ineligible":
            status = "not_prepared"; reasons.append("token_ineligible_not_prepared")
        elif upstream_status == "blocked":
            status = "blocked"; reasons.append("token_eligibility_blocked")
        elif upstream_status == "invalid":
            status = "invalid"; reasons.append("token_eligibility_invalid")
        elif authorized is None or expires is None or evaluated is None:
            reasons.append("token_eligibility_invalid")
            errors.append("invalid_authorized_at" if authorized is None else "invalid_expires_at" if expires is None else "invalid_evaluated_at")
        elif evaluated < authorized:
            status = "blocked"; reasons.append("authorization_not_yet_effective")
        elif evaluated >= expires:
            status = "expired"; reasons.append("token_eligibility_expired")
        elif prepared_time < authorized:
            status = "blocked"; reasons.append("authorization_not_yet_effective")
        elif prepared_time >= expires:
            status = "expired"; reasons.append("authorization_expired_before_preparation")
        else:
            status = "prepared"; reasons.append("token_eligibility_preparation_ready")

    ttl = eligibility.get("authorization_ttl_seconds")
    safe_ttl = ttl if isinstance(ttl, int) and not isinstance(ttl, bool) and 0 < ttl <= MAX_AUTHORIZATION_TTL_SECONDS else 1
    base: dict[str, Any] = {
        "schema": CAPABILITY_AUTHORIZATION_TOKEN_PREPARATION_SCHEMA,
        "status": status,
        **{name: name == status for name in TOKEN_PREPARATION_STATUSES},
        "prepared_at": prepared_text or "1970-01-01T00:00:00Z",
        "authorization_token_eligibility_id": _safe_text(eligibility.get("eligibility_id")),
        "authorization_token_eligibility_fingerprint": _safe_text(eligibility.get("fingerprint")),
        "authorization_token_eligibility_status": _safe_text(eligibility.get("status")),
        "active_authorization_id": _safe_text(eligibility.get("active_authorization_id")),
        "active_authorization_fingerprint": _safe_text(eligibility.get("active_authorization_fingerprint")),
        "active_authorization_status": _safe_text(eligibility.get("active_authorization_status")),
        "authorized_at": _timestamp(eligibility.get("authorized_at"))[0] or "1970-01-01T00:00:00Z",
        "expires_at": _timestamp(eligibility.get("expires_at"))[0] or "1970-01-01T00:00:01Z",
        "authorization_ttl_seconds": safe_ttl,
        "eligibility_evaluated_at": _timestamp(eligibility.get("evaluated_at"))[0] or "1970-01-01T00:00:00Z",
        "token_preparation_created": status == "prepared",
        **{name: False for name in _POST_PREPARATION_FLAGS},
        "reasons": sorted(set(reasons)), "errors": sorted(set(errors)),
    }
    for prefix in _LINEAGES:
        base[prefix + "_id"] = _safe_text(eligibility.get(prefix + "_id"))
        base[prefix + "_fingerprint"] = _safe_text(eligibility.get(prefix + "_fingerprint"))
    fingerprint = _hash(base)
    base["preparation_id"] = "capability-authorization-token-preparation-" + fingerprint[:24]
    base["fingerprint"] = fingerprint
    result = json.loads(canonical_json(base))
    from core.runtime.runtime_capability_authorization_token_preparation_validation import validate_capability_authorization_token_preparation
    if not validate_capability_authorization_token_preparation(result).valid:
        raise RuntimeError("internal token preparation validation failed")
    return result


__all__ = ["CAPABILITY_AUTHORIZATION_TOKEN_PREPARATION_SCHEMA", "TOKEN_PREPARATION_STATUSES", "prepare_capability_authorization_token"]
