from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping

from core.runtime.runtime_capability_bootstrap_plan import canonical_json
from core.runtime.runtime_capability_activation_authorization_request import REQUEST_SCHEMA
from core.runtime.runtime_capability_activation_authorization_request_validation import validate_authorization_review_request

CAPABILITY_ACTIVATION_AUTHORIZATION_REVIEW_DECISION_SCHEMA = "zero.runtime.capability_activation_authorization_review_decision.v1"
DECISIONS = frozenset({"approved", "denied", "blocked", "invalid"})
MAX_REVIEWER_ID_LENGTH = 256
MAX_REASON_LENGTH = 2048


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    result = " ".join(value.split())
    return result[:limit] if result else None


def _timestamp(value: Any) -> str | None:
    if value is None:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, datetime):
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


def _link(request: Mapping[str, Any], name: str, id_key: str) -> tuple[Any, Any]:
    value = request.get(name)
    if isinstance(value, Mapping):
        return value.get(id_key), value.get("fingerprint")
    return request.get(id_key), request.get(id_key.removesuffix("_id") + "_fingerprint")


def build_capability_activation_authorization_review_decision(
    *, authorization_review_request: Any, decision: Any, reviewer_id: Any,
    decision_reason: Any, reviewed_at: Any = None,
) -> dict[str, Any]:
    request = deepcopy(dict(authorization_review_request)) if isinstance(authorization_review_request, Mapping) else {}
    errors: list[str] = []
    request_validation = validate_authorization_review_request(request)
    if not request_validation.valid:
        errors.append("invalid_request")
    normalized_reviewer = _text(reviewer_id, MAX_REVIEWER_ID_LENGTH)
    normalized_reason = _text(decision_reason, MAX_REASON_LENGTH)
    normalized_time = _timestamp(reviewed_at)
    normalized_decision = decision if isinstance(decision, str) and decision in DECISIONS else "invalid"
    if normalized_reviewer is None: errors.append("invalid_reviewer")
    if not isinstance(decision, str) or decision not in DECISIONS: errors.append("invalid_decision")
    if normalized_reason is None: errors.append("invalid_reason")
    if normalized_time is None: errors.append("invalid_timestamp")
    if request_validation.valid and (request.get("reviewable") is False or request.get("review_status") in {"blocked", "rejected", "invalid", "unsupported"}):
        errors.append("request_not_reviewable")
    if "invalid_request" in errors or any(x in errors for x in ("invalid_reviewer", "invalid_decision", "invalid_reason", "invalid_timestamp")):
        normalized_decision = "invalid"
    elif "request_not_reviewable" in errors:
        normalized_decision = "blocked"

    policy = request.get("policy") if isinstance(request.get("policy"), Mapping) else {}
    handoff_id, handoff_fp = _link(request, "review_handoff_linkage", "handoff_id")
    review_id, review_fp = _link(request, "review_linkage", "review_id")
    eligibility_id, eligibility_fp = _link(request, "eligibility_linkage", "eligibility_id")
    proposal_id, proposal_fp = _link(request, "activation_proposal_linkage", "activation_proposal_id")
    profile_id, profile_fp = _link(request, "capability_profile_linkage", "capability_profile_id")
    strategy_id, strategy_fp = _link(request, "capability_strategy_linkage", "capability_strategy_id")
    base = {
        "schema": CAPABILITY_ACTIVATION_AUTHORIZATION_REVIEW_DECISION_SCHEMA,
        "decision": normalized_decision, "decision_reason": normalized_reason or "invalid_reason",
        "reviewer_id": normalized_reviewer or "invalid-reviewer", "reviewed_at": normalized_time,
        "authorization_review_request_id": request.get("request_id"), "authorization_review_request_fingerprint": request.get("fingerprint"),
        "review_policy_id": policy.get("policy_id"), "review_policy_fingerprint": policy.get("fingerprint"),
        "review_handoff_id": handoff_id, "review_handoff_fingerprint": handoff_fp,
        "review_id": review_id, "review_fingerprint": review_fp,
        "eligibility_id": eligibility_id, "eligibility_fingerprint": eligibility_fp,
        "activation_proposal_id": proposal_id, "activation_proposal_fingerprint": proposal_fp,
        "capability_profile_id": profile_id, "capability_profile_fingerprint": profile_fp,
        "capability_strategy_id": strategy_id, "capability_strategy_fingerprint": strategy_fp,
        "approved": normalized_decision == "approved", "denied": normalized_decision == "denied",
        "blocked": normalized_decision == "blocked", "invalid": normalized_decision == "invalid",
        "active_authorization_created": False, "token_issued": False, "runtime_activated": False,
        "execution_authority_granted": False, "errors": sorted(set(errors)),
    }
    identity = {k: v for k, v in base.items() if k not in {"decision_id", "fingerprint"}}
    fingerprint = _hash(identity)
    base["decision_id"] = "capability-activation-authorization-review-decision-" + fingerprint[:24]
    base["fingerprint"] = fingerprint
    return json.loads(canonical_json(base))


__all__ = ["CAPABILITY_ACTIVATION_AUTHORIZATION_REVIEW_DECISION_SCHEMA", "DECISIONS", "build_capability_activation_authorization_review_decision"]
