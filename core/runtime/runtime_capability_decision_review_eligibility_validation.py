from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_decision_review_eligibility import *
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityDecisionReviewEligibilityValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"contract","schema_version","decision_review_eligibility_id","decision_review_eligibility_fingerprint","decision_review_request_id","decision_review_request_fingerprint","decision_readiness_closure_id","decision_readiness_closure_fingerprint","decision_question","proposal_id","proposal_type","proposed_outcome","scope_checks","limitation_checks","permission_checks","claim_checks","eligibility_status","eligible","reasons","blocked_reasons"}
def validate_capability_decision_review_eligibility(v:Any)->CapabilityDecisionReviewEligibilityValidationResult:
 if not isinstance(v,Mapping):return CapabilityDecisionReviewEligibilityValidationResult(False,("eligibility_not_object",))
 e=[];s=v.get("eligibility_status")
 if set(v)!=_REQ:e.append("invalid_fields")
 if v.get("contract")!=CONTRACT or v.get("schema_version")!=SCHEMA_VERSION or s not in STATUSES or v.get("eligible") is not(s=="eligible"):e.append("invalid_contract_or_status")
 if s=="eligible" and any(not isinstance(v.get(n),Mapping) or v[n].get("valid") is not True for n in ("scope_checks","limitation_checks","permission_checks","claim_checks")):e.append("forbidden_success_transition")
 try:f=_hash({k:x for k,x in v.items() if k not in {"decision_review_eligibility_id","decision_review_eligibility_fingerprint"}})
 except (TypeError,ValueError):e.append("noncanonical_value")
 else:
  if v.get("decision_review_eligibility_fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("decision_review_eligibility_id")!="capability-decision-review-eligibility-"+f[:24]:e.append("id_mismatch")
 return CapabilityDecisionReviewEligibilityValidationResult(not e,tuple(dict.fromkeys(e)))
