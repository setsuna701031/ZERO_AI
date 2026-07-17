from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_decision_readiness_closure import *
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityDecisionReadinessClosureValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"contract","schema_version","decision_readiness_closure_id","decision_readiness_closure_fingerprint","authority_id","authority_fingerprint","execution_request_id","execution_request_fingerprint","bridge_closure_id","bridge_closure_fingerprint","observation_closure_id","observation_closure_fingerprint","consumer_acceptance_id","consumer_acceptance_fingerprint","relevance_assessment_id","relevance_assessment_fingerprint","sufficiency_assessment_id","sufficiency_assessment_fingerprint","decision_readiness_id","decision_readiness_fingerprint","decision_question","chain_validation_results","evidence_integrity_results","relevance_consistency_results","sufficiency_consistency_results","readiness_consistency_results","execution_completion_claim","authorization_claim","decision_made_claim","verification_status","closed","limitations","reasons","blocked_reasons","failure_reasons"}
def validate_capability_decision_readiness_closure(v:Any)->CapabilityDecisionReadinessClosureValidationResult:
 if not isinstance(v,Mapping):return CapabilityDecisionReadinessClosureValidationResult(False,("closure_not_object",))
 e=[];s=v.get("verification_status")
 if set(v)!=_REQ:e.append("invalid_fields")
 if v.get("contract")!=CONTRACT or v.get("schema_version")!=SCHEMA_VERSION or s not in STATUSES or v.get("closed") is not(s=="verified_closed"):e.append("invalid_contract_or_status")
 if any(v.get(n) is not False for n in ("execution_completion_claim","authorization_claim","decision_made_claim")):e.append("forbidden_claim")
 if not isinstance(v.get("limitations"),list) or any(not isinstance(x,str) or not x for x in v.get("limitations",[])):e.append("malformed_limitations")
 if s=="verified_closed" and any(not isinstance(v.get(n),Mapping) or v[n].get("valid") is not True for n in ("chain_validation_results","evidence_integrity_results","relevance_consistency_results","sufficiency_consistency_results","readiness_consistency_results")):e.append("forbidden_success_transition")
 try:f=_hash({k:x for k,x in v.items() if k not in {"decision_readiness_closure_id","decision_readiness_closure_fingerprint"}})
 except (TypeError,ValueError):e.append("noncanonical_value")
 else:
  if v.get("decision_readiness_closure_fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("decision_readiness_closure_id")!="capability-decision-readiness-closure-"+f[:24]:e.append("id_mismatch")
 return CapabilityDecisionReadinessClosureValidationResult(not e,tuple(dict.fromkeys(e)))
