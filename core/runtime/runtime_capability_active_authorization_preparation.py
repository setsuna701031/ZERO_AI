from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping

from core.runtime.runtime_capability_bootstrap_plan import canonical_json
from core.runtime.runtime_capability_active_authorization_eligibility_validation import (
    validate_capability_active_authorization_eligibility,
)

CAPABILITY_ACTIVE_AUTHORIZATION_PREPARATION_SCHEMA = (
    "zero.runtime.capability_active_authorization_preparation.v1"
)
PREPARATION_STATUSES = frozenset({"prepared", "not_prepared", "blocked", "invalid"})
_AUTHORITY_FLAGS = (
    "active_authorization_created",
    "authorization_granted",
    "token_issued",
    "runtime_activated",
    "execution_authority_granted",
)
_UPSTREAM_LINKAGES = (
    "authorization_review_decision",
    "authorization_review_request",
    "review_policy",
    "review_handoff",
    "review",
    "review_eligibility",
    "activation_proposal",
    "capability_profile",
    "capability_strategy",
)


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _timestamp(value: Any) -> str | None:
    if value is None:
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
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_text(value: Any) -> str:
    return value if isinstance(value, str) and value else "unavailable"


def prepare_capability_active_authorization(
    active_authorization_eligibility: Any, *, prepared_at: Any = None,
) -> dict[str, Any]:
    eligibility = (
        dict(active_authorization_eligibility)
        if isinstance(active_authorization_eligibility, Mapping)
        else {}
    )
    validation = validate_capability_active_authorization_eligibility(eligibility)
    timestamp = _timestamp(prepared_at)
    reasons: list[str] = []
    errors: list[str] = []
    status = "invalid"

    authority_violation = any(
        name in eligibility and eligibility.get(name) is not False
        for name in ("active_authorization_created", "token_issued", "runtime_activated", "execution_authority_granted")
    ) or any(
        name in eligibility
        for name in ("authorized", "activation_allowed", "may_execute", "runtime_permission", "authorization_issued", "activation_performed", "runtime_started")
    )
    if timestamp is None:
        errors.append("invalid_timestamp")
        reasons.append("eligibility_invalid")
    elif authority_violation:
        status = "blocked"
        reasons.append("authority_flag_violation")
        errors.append("authority_flag_violation")
    elif not validation.valid:
        reasons.append("eligibility_invalid")
        errors.append("invalid_eligibility")
        translations = {
            "invalid_schema": "invalid_schema",
            "eligibility_id_mismatch": "invalid_identity",
            "fingerprint_mismatch": "fingerprint_mismatch",
            "invalid_status": "invalid_status",
            "invalid_timestamp": "invalid_timestamp",
            "missing_linkage": "missing_linkage",
            "inconsistent_status_flags": "inconsistent_flags",
        }
        errors.extend(translations[item] for item in validation.errors if item in translations)
    else:
        upstream_status = eligibility["status"]
        if upstream_status == "eligible":
            status = "prepared"
            reasons.append("eligible_preparation_ready")
        elif upstream_status == "ineligible":
            status = "not_prepared"
            reasons.append("ineligible_not_prepared")
        elif upstream_status == "blocked":
            status = "blocked"
            reasons.append("eligibility_blocked")
            errors.extend(eligibility.get("errors", []))
        else:
            reasons.append("eligibility_invalid")
            errors.extend(eligibility.get("errors", []))

    base: dict[str, Any] = {
        "schema": CAPABILITY_ACTIVE_AUTHORIZATION_PREPARATION_SCHEMA,
        "status": status,
        "prepared": status == "prepared",
        "not_prepared": status == "not_prepared",
        "blocked": status == "blocked",
        "invalid": status == "invalid",
        "prepared_at": timestamp or "1970-01-01T00:00:00Z",
        "active_authorization_eligibility_id": _safe_text(eligibility.get("eligibility_id")),
        "active_authorization_eligibility_fingerprint": _safe_text(eligibility.get("fingerprint")),
        "active_authorization_eligibility_status": _safe_text(eligibility.get("status")),
        "active_authorization_created": False,
        "authorization_granted": False,
        "token_issued": False,
        "runtime_activated": False,
        "execution_authority_granted": False,
        "reasons": sorted(set(reasons)),
        "errors": sorted(set(errors)),
    }
    for prefix in _UPSTREAM_LINKAGES:
        base[prefix + "_id"] = _safe_text(eligibility.get(prefix + "_id"))
        base[prefix + "_fingerprint"] = _safe_text(eligibility.get(prefix + "_fingerprint"))

    fingerprint = _hash(base)
    base["preparation_id"] = "capability-active-authorization-preparation-" + fingerprint[:24]
    base["fingerprint"] = fingerprint
    result = json.loads(canonical_json(base))

    from core.runtime.runtime_capability_active_authorization_preparation_validation import (
        validate_capability_active_authorization_preparation,
    )
    if not validate_capability_active_authorization_preparation(result).valid:
        raise RuntimeError("internal preparation validation failed")
    return result


__all__ = [
    "CAPABILITY_ACTIVE_AUTHORIZATION_PREPARATION_SCHEMA",
    "PREPARATION_STATUSES",
    "prepare_capability_active_authorization",
]
