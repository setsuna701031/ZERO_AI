from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from core.runtime.runtime_capability_activation_authorization_review_decision import CAPABILITY_ACTIVATION_AUTHORIZATION_REVIEW_DECISION_SCHEMA, DECISIONS, _hash

@dataclass(frozen=True)
class CapabilityActivationAuthorizationReviewDecisionValidationResult:
    valid: bool
    errors: tuple[str, ...]

def validate_capability_activation_authorization_review_decision(value: Any) -> CapabilityActivationAuthorizationReviewDecisionValidationResult:
    if not isinstance(value, Mapping):
        return CapabilityActivationAuthorizationReviewDecisionValidationResult(False, ("decision_not_object",))
    errors: list[str] = []
    required = {"schema","decision_id","decision","decision_reason","reviewer_id","reviewed_at","authorization_review_request_id","authorization_review_request_fingerprint","review_policy_id","review_policy_fingerprint","review_handoff_id","review_handoff_fingerprint","review_id","review_fingerprint","eligibility_id","eligibility_fingerprint","activation_proposal_id","activation_proposal_fingerprint","capability_profile_id","capability_profile_fingerprint","capability_strategy_id","capability_strategy_fingerprint","approved","denied","blocked","invalid","active_authorization_created","token_issued","runtime_activated","execution_authority_granted","errors","fingerprint"}
    if set(value) != required: errors.append("invalid_fields")
    if value.get("schema") != CAPABILITY_ACTIVATION_AUTHORIZATION_REVIEW_DECISION_SCHEMA: errors.append("invalid_schema")
    decision = value.get("decision")
    if decision not in DECISIONS: errors.append("invalid_decision")
    if not isinstance(value.get("reviewer_id"), str) or not value.get("reviewer_id", "").strip(): errors.append("invalid_reviewer")
    if not isinstance(value.get("decision_reason"), str) or not value.get("decision_reason", "").strip(): errors.append("invalid_reason")
    try:
        parsed = datetime.fromisoformat(value.get("reviewed_at", "").replace("Z", "+00:00"))
        if parsed.tzinfo is None: raise ValueError
    except (AttributeError, TypeError, ValueError): errors.append("invalid_timestamp")
    if any(value.get(k) is not False for k in ("active_authorization_created","token_issued","runtime_activated","execution_authority_granted")): errors.append("authority_granted")
    flags = {name: value.get(name) for name in DECISIONS}
    if any(v is not (k == decision) for k, v in flags.items()): errors.append("inconsistent_decision_flags")
    for prefix in ("authorization_review_request","review_policy"):
        if not isinstance(value.get(prefix + "_id"), str) or not isinstance(value.get(prefix + "_fingerprint"), str): errors.append("missing_linkage")
    try:
        expected = _hash({k: v for k, v in value.items() if k not in {"decision_id","fingerprint"}})
        if value.get("fingerprint") != expected: errors.append("fingerprint_mismatch")
        if value.get("decision_id") != "capability-activation-authorization-review-decision-" + expected[:24]: errors.append("decision_id_mismatch")
    except (TypeError, ValueError): errors.append("noncanonical_value")
    return CapabilityActivationAuthorizationReviewDecisionValidationResult(not errors, tuple(dict.fromkeys(errors)))

validate_authorization_review_decision = validate_capability_activation_authorization_review_decision
__all__ = ["CapabilityActivationAuthorizationReviewDecisionValidationResult", "validate_capability_activation_authorization_review_decision", "validate_authorization_review_decision"]
