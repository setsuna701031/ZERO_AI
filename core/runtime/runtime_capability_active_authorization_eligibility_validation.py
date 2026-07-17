from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Mapping

from core.runtime.runtime_capability_active_authorization_eligibility import CAPABILITY_ACTIVE_AUTHORIZATION_ELIGIBILITY_SCHEMA, ELIGIBILITY_STATUSES, _AUTHORITY_FLAGS, _LINKAGES, _hash

@dataclass(frozen=True)
class CapabilityActiveAuthorizationEligibilityValidationResult:
    valid: bool
    errors: tuple[str, ...]

_BASE_FIELDS = {"schema","eligibility_id","status","eligible","ineligible","blocked","invalid","evaluated_at","authorization_review_decision_id","authorization_review_decision_fingerprint","authorization_review_decision_status","active_authorization_created","token_issued","runtime_activated","execution_authority_granted","reasons","errors","fingerprint"}
_REQUIRED = _BASE_FIELDS | {prefix + suffix for prefix, _ in _LINKAGES for suffix in ("_id","_fingerprint")}
_FORGED_AUTHORITY = frozenset({"authorized","activation_allowed","may_execute","runtime_permission","authorization_issued","activation_performed","runtime_started"})

def validate_capability_active_authorization_eligibility(value: Any) -> CapabilityActiveAuthorizationEligibilityValidationResult:
    if not isinstance(value, Mapping): return CapabilityActiveAuthorizationEligibilityValidationResult(False,("eligibility_not_object",))
    errors: list[str] = []
    keys = set(value)
    if keys != _REQUIRED: errors.append("invalid_fields")
    if keys & _FORGED_AUTHORITY: errors.append("forged_authority_field")
    if value.get("schema") != CAPABILITY_ACTIVE_AUTHORIZATION_ELIGIBILITY_SCHEMA: errors.append("invalid_schema")
    status = value.get("status")
    if status not in ELIGIBILITY_STATUSES: errors.append("invalid_status")
    if any(value.get(name) is not (name == status) for name in ELIGIBILITY_STATUSES): errors.append("inconsistent_status_flags")
    try:
        parsed=datetime.fromisoformat(value.get("evaluated_at","").replace("Z","+00:00"))
        if parsed.tzinfo is None: raise ValueError
    except (AttributeError,TypeError,ValueError): errors.append("invalid_timestamp")
    for prefix in ("authorization_review_decision",) + tuple(x for x,_ in _LINKAGES):
        if not isinstance(value.get(prefix+"_id"),str) or not value.get(prefix+"_id") or not isinstance(value.get(prefix+"_fingerprint"),str) or not value.get(prefix+"_fingerprint"): errors.append("missing_linkage")
    if any(value.get(k) is not False for k in _AUTHORITY_FLAGS): errors.append("authority_flag_violation")
    for name in ("reasons","errors"):
        item=value.get(name)
        if not isinstance(item,list) or item != sorted(set(item)) or any(not isinstance(x,str) or not x or len(x)>128 or not re.fullmatch(r"[a-z0-9_]+",x) for x in item): errors.append("invalid_"+name)
    try:
        expected=_hash({k:v for k,v in value.items() if k not in {"eligibility_id","fingerprint"}})
        if value.get("fingerprint") != expected: errors.append("fingerprint_mismatch")
        if value.get("eligibility_id") != "capability-active-authorization-eligibility-"+expected[:24]: errors.append("eligibility_id_mismatch")
    except (TypeError,ValueError): errors.append("noncanonical_value")
    return CapabilityActiveAuthorizationEligibilityValidationResult(not errors,tuple(dict.fromkeys(errors)))

__all__=["CapabilityActiveAuthorizationEligibilityValidationResult","validate_capability_active_authorization_eligibility"]
