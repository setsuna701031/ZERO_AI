from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping

from core.runtime.runtime_capability_bootstrap_plan import canonical_json
from core.runtime.runtime_capability_active_authorization import MAX_AUTHORIZATION_TTL_SECONDS
from core.runtime.runtime_capability_active_authorization_validation import (
    validate_capability_active_authorization,
)

CAPABILITY_AUTHORIZATION_TOKEN_ELIGIBILITY_SCHEMA = (
    "zero.runtime.capability_authorization_token_eligibility.v1"
)
TOKEN_ELIGIBILITY_STATUSES = frozenset(
    {"eligible", "ineligible", "blocked", "invalid", "expired"}
)
_LINEAGES = (
    "active_authorization_preparation", "active_authorization_eligibility",
    "authorization_review_decision", "authorization_review_request", "review_policy",
    "review_handoff", "review", "review_eligibility", "activation_proposal",
    "capability_profile", "capability_strategy",
)
_DOWNSTREAM_FLAGS = (
    "token_preparation_created", "token_created", "token_issued", "token_signed",
    "runtime_activated", "execution_authority_granted",
)
_FORBIDDEN_FIELDS = frozenset({
    "token_value", "token_secret", "signature", "private_key", "public_key",
    "bearer", "credential", "may_execute", "executor_allowed", "activation_allowed",
    "execution_allowed", "runtime_started", "activation_complete",
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


def evaluate_capability_authorization_token_eligibility(
    active_authorization: Any, *, evaluated_at: Any = None,
) -> dict[str, Any]:
    authorization = dict(active_authorization) if isinstance(active_authorization, Mapping) else {}
    evaluated_text, evaluated = _timestamp(evaluated_at, default_now=True)
    validation = validate_capability_active_authorization(authorization)
    reasons: list[str] = []
    errors: list[str] = []
    status = "invalid"

    authority_violation = any(
        name in authorization and authorization.get(name) is not False
        for name in ("token_issued", "runtime_activated", "execution_authority_granted")
    ) or bool(set(authorization) & _FORBIDDEN_FIELDS)

    if evaluated_text is None or evaluated is None:
        reasons.append("authorization_invalid")
        errors.append("invalid_evaluated_at")
    elif authority_violation:
        status = "blocked"
        reasons.append("authority_flag_violation")
        errors.append("token_state_violation")
    elif not validation.valid:
        reasons.append("authorization_invalid")
        errors.append("invalid_authorization")
        translations = {
            "invalid_schema": "invalid_schema", "authorization_id_mismatch": "invalid_identity",
            "fingerprint_mismatch": "fingerprint_mismatch", "invalid_status": "invalid_status",
            "invalid_authorized_at": "invalid_authorized_at", "invalid_expires_at": "invalid_expires_at",
            "invalid_ttl": "invalid_ttl", "ttl_mismatch": "invalid_ttl",
            "missing_linkage": "missing_linkage", "inconsistent_status_flags": "inconsistent_flags",
            "inconsistent_authority_flags": "inconsistent_flags",
        }
        errors.extend(translations[item] for item in validation.errors if item in translations)
    else:
        authorized_text, authorized = _timestamp(authorization["authorized_at"])
        expires_text, expires = _timestamp(authorization["expires_at"])
        upstream_status = authorization["status"]
        if upstream_status == "expired":
            status = "expired"; reasons.append("authorization_expired")
        elif upstream_status == "not_authorized":
            status = "ineligible"; reasons.append("not_authorized_token_ineligible")
        elif upstream_status == "blocked":
            status = "blocked"; reasons.append("authorization_blocked")
        elif upstream_status == "invalid":
            status = "invalid"; reasons.append("authorization_invalid")
        elif authorized is None or expires is None:
            errors.append("invalid_authorized_at" if authorized is None else "invalid_expires_at")
            reasons.append("authorization_invalid")
        elif evaluated < authorized:
            status = "blocked"; reasons.append("authorization_not_yet_effective")
        elif evaluated >= expires:
            status = "expired"; reasons.append("authorization_expired")
        else:
            status = "eligible"; reasons.append("active_authorization_token_eligible")

    base: dict[str, Any] = {
        "schema": CAPABILITY_AUTHORIZATION_TOKEN_ELIGIBILITY_SCHEMA,
        "status": status,
        **{name: name == status for name in TOKEN_ELIGIBILITY_STATUSES},
        "evaluated_at": evaluated_text or "1970-01-01T00:00:00Z",
        "active_authorization_id": _safe_text(authorization.get("authorization_id")),
        "active_authorization_fingerprint": _safe_text(authorization.get("fingerprint")),
        "active_authorization_status": _safe_text(authorization.get("status")),
        "authorized_at": _timestamp(authorization.get("authorized_at"))[0] or "1970-01-01T00:00:00Z",
        "expires_at": _timestamp(authorization.get("expires_at"))[0] or "1970-01-01T00:00:01Z",
        "authorization_ttl_seconds": authorization.get("authorization_ttl_seconds")
        if isinstance(authorization.get("authorization_ttl_seconds"), int)
        and not isinstance(authorization.get("authorization_ttl_seconds"), bool)
        and 0 < authorization["authorization_ttl_seconds"] <= MAX_AUTHORIZATION_TTL_SECONDS else 1,
        "token_eligibility_confirmed": status == "eligible",
        **{name: False for name in _DOWNSTREAM_FLAGS},
        "reasons": sorted(set(reasons)), "errors": sorted(set(errors)),
    }
    for prefix in _LINEAGES:
        base[prefix + "_id"] = _safe_text(authorization.get(prefix + "_id"))
        base[prefix + "_fingerprint"] = _safe_text(authorization.get(prefix + "_fingerprint"))
    fingerprint = _hash(base)
    base["eligibility_id"] = "capability-authorization-token-eligibility-" + fingerprint[:24]
    base["fingerprint"] = fingerprint
    result = json.loads(canonical_json(base))
    from core.runtime.runtime_capability_authorization_token_eligibility_validation import (
        validate_capability_authorization_token_eligibility,
    )
    if not validate_capability_authorization_token_eligibility(result).valid:
        raise RuntimeError("internal token eligibility validation failed")
    return result


__all__ = [
    "CAPABILITY_AUTHORIZATION_TOKEN_ELIGIBILITY_SCHEMA", "TOKEN_ELIGIBILITY_STATUSES",
    "evaluate_capability_authorization_token_eligibility",
]
