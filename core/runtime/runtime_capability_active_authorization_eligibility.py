from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping

from core.runtime.runtime_capability_bootstrap_plan import canonical_json
from core.runtime.runtime_capability_activation_authorization_review_decision_validation import validate_capability_activation_authorization_review_decision

CAPABILITY_ACTIVE_AUTHORIZATION_ELIGIBILITY_SCHEMA = "zero.runtime.capability_active_authorization_eligibility.v1"
ELIGIBILITY_STATUSES = frozenset({"eligible", "ineligible", "blocked", "invalid"})
_AUTHORITY_FLAGS = ("active_authorization_created", "token_issued", "runtime_activated", "execution_authority_granted")
_LINKAGES = (
    ("authorization_review_request", "authorization_review_request"),
    ("review_policy", "review_policy"),
    ("review_handoff", "review_handoff"),
    ("review", "review"),
    ("review_eligibility", "eligibility"),
    ("activation_proposal", "activation_proposal"),
    ("capability_profile", "capability_profile"),
    ("capability_strategy", "capability_strategy"),
)

def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()

def _timestamp(value: Any) -> str | None:
    if value is None:
        parsed = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try: parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError: return None
    else: return None
    if parsed.tzinfo is None or parsed.utcoffset() is None: return None
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def _safe_text(value: Any) -> str:
    return value if isinstance(value, str) and value else "unavailable"

def evaluate_capability_active_authorization_eligibility(
    authorization_review_decision: Any, *, evaluated_at: Any = None,
) -> dict[str, Any]:
    decision = dict(authorization_review_decision) if isinstance(authorization_review_decision, Mapping) else {}
    validation = validate_capability_activation_authorization_review_decision(decision)
    timestamp = _timestamp(evaluated_at)
    errors: list[str] = []
    reasons: list[str] = []
    status = "invalid"
    if timestamp is None:
        errors.append("invalid_timestamp")
    if not validation.valid:
        errors.append("invalid_decision")
        if "fingerprint_mismatch" in validation.errors: errors.append("fingerprint_mismatch")
        if "decision_id_mismatch" in validation.errors: errors.append("invalid_identity")
        if "missing_linkage" in validation.errors: errors.append("missing_linkage")
        if "authority_granted" in validation.errors: errors.append("authority_flag_violation")
        reasons.append("malformed_decision")
    elif decision["decision"] == "approved":
        status = "eligible"; reasons.append("approved_decision_eligible")
    elif decision["decision"] == "denied":
        status = "ineligible"; reasons.append("denied_decision_ineligible")
    elif decision["decision"] == "blocked":
        status = "blocked"; reasons.append("blocked_decision")
        if decision.get("errors"): errors.append("policy_precondition_blocked")
    else:
        status = "invalid"; reasons.append("invalid_decision")
        errors.extend(x for x in decision.get("errors", []) if isinstance(x, str))
    missing = []
    for output, source in _LINKAGES:
        if not isinstance(decision.get(source + "_id"), str) or not isinstance(decision.get(source + "_fingerprint"), str):
            missing.append(output)
    if validation.valid and missing:
        status = "invalid"; reasons = ["linkage_inconsistent"]; errors.append("missing_linkage")
    if validation.valid and any(decision.get(k) is not False for k in _AUTHORITY_FLAGS):
        status = "blocked"; reasons = ["authority_flag_violation"]; errors.append("authority_flag_violation")
    if timestamp is None:
        status = "invalid"; reasons = ["invalid_evaluation_timestamp"]

    base: dict[str, Any] = {
        "schema": CAPABILITY_ACTIVE_AUTHORIZATION_ELIGIBILITY_SCHEMA, "status": status,
        "eligible": status == "eligible", "ineligible": status == "ineligible",
        "blocked": status == "blocked", "invalid": status == "invalid",
        "evaluated_at": timestamp or "1970-01-01T00:00:00Z",
        "authorization_review_decision_id": _safe_text(decision.get("decision_id")),
        "authorization_review_decision_fingerprint": _safe_text(decision.get("fingerprint")),
        "authorization_review_decision_status": _safe_text(decision.get("decision")),
        "active_authorization_created": False, "token_issued": False,
        "runtime_activated": False, "execution_authority_granted": False,
        "reasons": sorted(set(reasons)), "errors": sorted(set(errors)),
    }
    for output, source in _LINKAGES:
        base[output + "_id"] = _safe_text(decision.get(source + "_id"))
        base[output + "_fingerprint"] = _safe_text(decision.get(source + "_fingerprint"))
    fingerprint = _hash(base)
    base["eligibility_id"] = "capability-active-authorization-eligibility-" + fingerprint[:24]
    base["fingerprint"] = fingerprint
    return json.loads(canonical_json(base))

__all__ = ["CAPABILITY_ACTIVE_AUTHORIZATION_ELIGIBILITY_SCHEMA", "ELIGIBILITY_STATUSES", "evaluate_capability_active_authorization_eligibility"]
