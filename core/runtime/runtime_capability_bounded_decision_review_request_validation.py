from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_bounded_decision_review_request import *
from core.runtime.runtime_capability_bounded_decision_review_request import _proposal_shape,_scope_contained
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityBoundedDecisionReviewRequestValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"contract","schema_version","decision_review_request_id","decision_review_request_fingerprint","decision_readiness_closure_id","decision_readiness_closure_fingerprint","authority_id","authority_fingerprint","execution_request_id","execution_request_fingerprint","observation_closure_id","observation_closure_fingerprint","decision_question","decision_proposal","requested_scope","requested_effect_class","requested_permissions","review_status","accepted","reasons","blocked_reasons"}
def validate_capability_bounded_decision_review_request(v:Any)->CapabilityBoundedDecisionReviewRequestValidationResult:
 if not isinstance(v,Mapping):return CapabilityBoundedDecisionReviewRequestValidationResult(False,("review_request_not_object",))
 e=[];s=v.get("review_status");p=v.get("decision_proposal");q=v.get("decision_question");perms=v.get("requested_permissions")
 if set(v)!=_REQ:e.append("invalid_fields")
 if v.get("contract")!=CONTRACT or v.get("schema_version")!=SCHEMA_VERSION or s not in STATUSES or v.get("accepted") is not(s=="accepted"):e.append("invalid_contract_or_status")
 if not _proposal_shape(p) or not isinstance(q,Mapping) or p.get("target_reference")!=q.get("target_reference"):e.append("proposal_or_target_mismatch")
 if v.get("requested_effect_class") not in EFFECT_CLASSES or not isinstance(perms,Mapping) or set(perms)!=PERMISSION_FIELDS or any(x is not False for x in perms.values()):e.append("permission_or_effect_violation")
 if not _scope_contained(v.get("requested_scope"),q.get("decision_scope",{}) if isinstance(q,Mapping) else {}) or not all(x in p.get("limitations_acknowledged",[]) for x in q.get("limitations",[]) if isinstance(q,Mapping)):e.append("scope_or_limitation_violation")
 try:f=_hash({k:x for k,x in v.items() if k not in {"decision_review_request_id","decision_review_request_fingerprint"}})
 except (TypeError,ValueError):e.append("noncanonical_value")
 else:
  if v.get("decision_review_request_fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("decision_review_request_id")!="capability-bounded-decision-review-request-"+f[:24]:e.append("id_mismatch")
 return CapabilityBoundedDecisionReviewRequestValidationResult(not e,tuple(dict.fromkeys(e)))
