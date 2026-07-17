from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_decision_authorization import *
from core.runtime.runtime_capability_bounded_decision_review_request import PERMISSION_FIELDS,PROPOSAL_OUTCOMES
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityDecisionAuthorizationValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"contract","schema_version","decision_authorization_id","decision_authorization_fingerprint","decision_policy_evaluation_id","decision_policy_evaluation_fingerprint","decision_review_eligibility_id","decision_review_eligibility_fingerprint","decision_review_request_id","decision_review_request_fingerprint","decision_readiness_closure_id","decision_readiness_closure_fingerprint","proposal_id","proposal_type","authorized_outcome","authorized_scope","authorized_effect_class","authorized_permissions","authorized_next_stage","authorization_status","authorized","execution_completion_claim","mutation_authorization_claim","external_execution_authorization_claim","limitations","reasons","blocked_reasons"}
def validate_capability_decision_authorization(v:Any)->CapabilityDecisionAuthorizationValidationResult:
 if not isinstance(v,Mapping):return CapabilityDecisionAuthorizationValidationResult(False,("authorization_not_object",))
 e=[];s=v.get("authorization_status");p=v.get("authorized_permissions");ptype=v.get("proposal_type")
 if set(v)!=_REQ:e.append("invalid_fields")
 if v.get("contract")!=CONTRACT or v.get("schema_version")!=SCHEMA_VERSION or s not in STATUSES or v.get("authorized") is not(s=="authorized"):e.append("invalid_contract_or_status")
 if any(v.get(n) is not False for n in ("execution_completion_claim","mutation_authorization_claim","external_execution_authorization_claim")):e.append("forbidden_claim")
 if not isinstance(p,Mapping) or set(p)!=PERMISSION_FIELDS or any(x is not False for x in p.values()):e.append("permission_violation")
 if s=="authorized" and (v.get("authorized_next_stage")!=NEXT_STAGES.get(ptype) or v.get("authorized_outcome")!=PROPOSAL_OUTCOMES.get(ptype)):e.append("authorization_mapping_mismatch")
 try:f=_hash({k:x for k,x in v.items() if k not in {"decision_authorization_id","decision_authorization_fingerprint"}})
 except (TypeError,ValueError):e.append("noncanonical_value")
 else:
  if v.get("decision_authorization_fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("decision_authorization_id")!="capability-decision-authorization-"+f[:24]:e.append("id_mismatch")
 return CapabilityDecisionAuthorizationValidationResult(not e,tuple(dict.fromkeys(e)))
