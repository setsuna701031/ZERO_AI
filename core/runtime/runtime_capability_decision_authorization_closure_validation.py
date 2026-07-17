from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_decision_authorization_closure import *
from core.runtime.runtime_capability_decision_authorization import NEXT_STAGES
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityDecisionAuthorizationClosureValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"contract","schema_version","decision_authorization_closure_id","decision_authorization_closure_fingerprint","authority_id","authority_fingerprint","execution_request_id","execution_request_fingerprint","observation_closure_id","observation_closure_fingerprint","decision_readiness_closure_id","decision_readiness_closure_fingerprint","decision_review_request_id","decision_review_request_fingerprint","decision_review_eligibility_id","decision_review_eligibility_fingerprint","decision_policy_evaluation_id","decision_policy_evaluation_fingerprint","decision_authorization_id","decision_authorization_fingerprint","decision_question","proposal_id","proposal_type","proposed_outcome","target_reference","chain_validation_results","scope_consistency_results","policy_consistency_results","permission_invariant_results","limitation_preservation_results","claim_invariant_results","execution_completion_claim","mutation_authorization_claim","external_execution_authorization_claim","decision_executed_claim","verification_status","closed","authorized_next_stage","limitations","reasons","blocked_reasons","failure_reasons"}
def validate_capability_decision_authorization_closure(v:Any)->CapabilityDecisionAuthorizationClosureValidationResult:
 if not isinstance(v,Mapping):return CapabilityDecisionAuthorizationClosureValidationResult(False,("authorization_closure_not_object",))
 e=[];s=v.get("verification_status")
 if set(v)!=_REQ:e.append("invalid_fields")
 if v.get("contract")!=CONTRACT or v.get("schema_version")!=SCHEMA_VERSION or s not in STATUSES or v.get("closed") is not(s=="verified_closed"):e.append("invalid_contract_or_status")
 if any(v.get(n) is not False for n in ("execution_completion_claim","mutation_authorization_claim","external_execution_authorization_claim","decision_executed_claim")):e.append("forbidden_claim")
 if v.get("authorized_next_stage") not in set(NEXT_STAGES.values())|{"blocked","invalid"} or not isinstance(v.get("limitations"),list):e.append("invalid_stage_or_limitations")
 if s=="verified_closed" and any(not isinstance(v.get(n),Mapping) or v[n].get("valid") is not True for n in ("chain_validation_results","scope_consistency_results","policy_consistency_results","permission_invariant_results","limitation_preservation_results","claim_invariant_results")):e.append("forbidden_success_transition")
 try:f=_hash({k:x for k,x in v.items() if k not in {"decision_authorization_closure_id","decision_authorization_closure_fingerprint"}})
 except (TypeError,ValueError):e.append("noncanonical_value")
 else:
  if v.get("decision_authorization_closure_fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("decision_authorization_closure_id")!="capability-decision-authorization-closure-"+f[:24]:e.append("id_mismatch")
 return CapabilityDecisionAuthorizationClosureValidationResult(not e,tuple(dict.fromkeys(e)))
