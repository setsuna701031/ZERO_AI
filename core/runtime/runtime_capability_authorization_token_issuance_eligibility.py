from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping

from core.runtime.runtime_capability_bootstrap_plan import canonical_json

CAPABILITY_AUTHORIZATION_TOKEN_ISSUANCE_ELIGIBILITY_SCHEMA = (
    "zero.runtime.capability_authorization_token_issuance_eligibility.v1"
)
TOKEN_ISSUANCE_ELIGIBILITY_STATUSES = frozenset(
    {"eligible", "ineligible", "blocked", "invalid", "expired"}
)
_LINEAGES = (
    "active_authorization_preparation", "active_authorization_eligibility",
    "authorization_review_decision", "authorization_review_request", "review_policy",
    "review_handoff", "review", "review_eligibility", "activation_proposal",
    "capability_profile", "capability_strategy",
)
_DOWNSTREAM_FLAGS = (
    "issuance_preparation_created", "token_issued", "token_signed",
    "token_handed_off", "token_material_created", "runtime_activated",
    "execution_authority_granted",
)
_FORBIDDEN_FIELDS = frozenset({
    "token_value", "token_secret", "bearer_token", "bearer", "credential", "api_key",
    "session_key", "private_key", "public_key", "signature", "signed_payload", "mac",
    "nonce", "random_bytes", "delivery_target", "executor_ticket", "may_execute",
    "executor_allowed", "activation_allowed", "execution_allowed", "runtime_started",
    "activation_complete",
})


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _timestamp(value: Any, *, default_now: bool = False) -> tuple[str | None, datetime | None]:
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
        return None, None
    parsed = parsed.astimezone(timezone.utc)
    return parsed.isoformat().replace("+00:00", "Z"), parsed


def _safe_text(value: Any) -> str:
    return value if isinstance(value, str) and value else "unavailable"


def evaluate_capability_authorization_token_issuance_eligibility(
    authorization_token: Any, *, evaluated_at: Any = None,
) -> dict[str, Any]:
    token = dict(authorization_token) if isinstance(authorization_token, Mapping) else {}
    evaluated_text, evaluated = _timestamp(evaluated_at, default_now=True)
    from core.runtime.runtime_capability_authorization_token_validation import (
        validate_capability_authorization_token,
    )
    validation = validate_capability_authorization_token(token)
    reasons: list[str] = []
    errors: list[str] = []
    status = "invalid"
    authority_violation = any(
        name in token and token.get(name) is not False
        for name in ("token_material_created", "token_signed", "token_issued", "token_handed_off", "runtime_activated", "execution_authority_granted")
    ) or bool(set(token) & _FORBIDDEN_FIELDS)

    if evaluated_text is None or evaluated is None:
        reasons.append("token_invalid"); errors.append("invalid_evaluated_at")
    elif authority_violation:
        status = "blocked"; reasons.append("authority_flag_violation"); errors.append("token_state_violation")
    elif not validation.valid:
        reasons.append("token_invalid"); errors.append("invalid_token")
        translations = {
            "invalid_schema": "invalid_schema", "token_id_mismatch": "invalid_identity",
            "fingerprint_mismatch": "fingerprint_mismatch", "invalid_status": "invalid_status",
            "invalid_created_at": "invalid_created_at", "invalid_expires_at": "invalid_token_expiry",
            "invalid_token_ttl": "invalid_token_ttl", "ttl_mismatch": "invalid_token_ttl",
            "invalid_authorization_expires_at": "invalid_authorization_expiry",
            "token_expiry_exceeds_authorization": "invalid_authorization_expiry",
            "missing_linkage": "missing_linkage", "inconsistent_status_flags": "inconsistent_flags",
            "inconsistent_token_created": "inconsistent_flags", "token_state_violation": "token_state_violation",
        }
        errors.extend(translations[item] for item in validation.errors if item in translations)
    else:
        _, created = _timestamp(token["created_at"])
        _, token_expiry = _timestamp(token["expires_at"])
        _, authorization_expiry = _timestamp(token["authorization_expires_at"])
        upstream = token["status"]
        if upstream == "not_created": status = "ineligible"; reasons.append("token_not_created_issuance_ineligible")
        elif upstream == "blocked": status = "blocked"; reasons.append("token_blocked")
        elif upstream == "invalid": status = "invalid"; reasons.append("token_invalid")
        elif upstream == "expired": status = "expired"; reasons.append("token_expired")
        elif created is None: reasons.append("token_invalid"); errors.append("invalid_created_at")
        elif token_expiry is None: reasons.append("token_invalid"); errors.append("invalid_token_expiry")
        elif authorization_expiry is None: reasons.append("token_invalid"); errors.append("invalid_authorization_expiry")
        elif evaluated < created: status = "blocked"; reasons.append("token_not_yet_effective")
        elif evaluated >= token_expiry: status = "expired"; reasons.append("token_expired")
        elif evaluated >= authorization_expiry: status = "expired"; reasons.append("authorization_expired_before_issuance")
        else: status = "eligible"; reasons.append("token_issuance_eligible")

    epoch = "1970-01-01T00:00:00Z"
    next_second = "1970-01-01T00:00:01Z"
    token_created = _timestamp(token.get("created_at"))[0] or epoch
    token_expires = _timestamp(token.get("expires_at"))[0] or next_second
    authorized = _timestamp(token.get("authorized_at"))[0] or epoch
    authorization_expires = _timestamp(token.get("authorization_expires_at"))[0] or next_second
    token_ttl = token.get("token_ttl_seconds")
    if not isinstance(token_ttl, int) or isinstance(token_ttl, bool) or token_ttl <= 0: token_ttl = 1
    authorization_ttl = token.get("authorization_ttl_seconds")
    if not isinstance(authorization_ttl, int) or isinstance(authorization_ttl, bool) or authorization_ttl <= 0: authorization_ttl = 1
    base: dict[str, Any] = {
        "schema": CAPABILITY_AUTHORIZATION_TOKEN_ISSUANCE_ELIGIBILITY_SCHEMA,
        "status": status, **{name: name == status for name in TOKEN_ISSUANCE_ELIGIBILITY_STATUSES},
        "evaluated_at": evaluated_text or epoch,
        "authorization_token_id": _safe_text(token.get("token_id")),
        "authorization_token_fingerprint": _safe_text(token.get("fingerprint")),
        "authorization_token_status": _safe_text(token.get("status")),
        "token_created_at": token_created, "token_expires_at": token_expires,
        "token_ttl_seconds": token_ttl,
        "authorization_token_preparation_id": _safe_text(token.get("authorization_token_preparation_id")),
        "authorization_token_preparation_fingerprint": _safe_text(token.get("authorization_token_preparation_fingerprint")),
        "authorization_token_preparation_status": _safe_text(token.get("authorization_token_preparation_status")),
        "token_prepared_at": _timestamp(token.get("token_prepared_at"))[0] or epoch,
        "authorization_token_eligibility_id": _safe_text(token.get("authorization_token_eligibility_id")),
        "authorization_token_eligibility_fingerprint": _safe_text(token.get("authorization_token_eligibility_fingerprint")),
        "authorization_token_eligibility_status": _safe_text(token.get("authorization_token_eligibility_status")),
        "token_eligibility_evaluated_at": _timestamp(token.get("token_eligibility_evaluated_at"))[0] or epoch,
        "active_authorization_id": _safe_text(token.get("active_authorization_id")),
        "active_authorization_fingerprint": _safe_text(token.get("active_authorization_fingerprint")),
        "active_authorization_status": _safe_text(token.get("active_authorization_status")),
        "authorized_at": authorized, "authorization_expires_at": authorization_expires,
        "authorization_ttl_seconds": authorization_ttl,
        "issuance_eligibility_confirmed": status == "eligible",
        **{name: False for name in _DOWNSTREAM_FLAGS},
        "reasons": sorted(set(reasons)), "errors": sorted(set(errors)),
    }
    for prefix in _LINEAGES:
        base[prefix + "_id"] = _safe_text(token.get(prefix + "_id"))
        base[prefix + "_fingerprint"] = _safe_text(token.get(prefix + "_fingerprint"))
    fingerprint = _hash(base)
    base["eligibility_id"] = "capability-authorization-token-issuance-eligibility-" + fingerprint[:24]
    base["fingerprint"] = fingerprint
    result = json.loads(canonical_json(base))
    from core.runtime.runtime_capability_authorization_token_issuance_eligibility_validation import (
        validate_capability_authorization_token_issuance_eligibility,
    )
    if not validate_capability_authorization_token_issuance_eligibility(result).valid:
        raise RuntimeError("internal token issuance eligibility validation failed")
    return result


__all__ = [
    "CAPABILITY_AUTHORIZATION_TOKEN_ISSUANCE_ELIGIBILITY_SCHEMA",
    "TOKEN_ISSUANCE_ELIGIBILITY_STATUSES",
    "evaluate_capability_authorization_token_issuance_eligibility",
]
