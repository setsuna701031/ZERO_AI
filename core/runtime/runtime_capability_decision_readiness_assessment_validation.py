from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_decision_readiness_assessment import *
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityDecisionReadinessAssessmentValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"contract","schema_version","decision_readiness_id","decision_readiness_fingerprint","consumer_acceptance_id","consumer_acceptance_fingerprint","relevance_assessment_id","relevance_assessment_fingerprint","sufficiency_assessment_id","sufficiency_assessment_fingerprint","observation_closure_id","observation_closure_fingerprint","decision_question","readiness_checks","decision_status","ready","execution_completion_claim","authorization_claim","recommended_next_stage","limitations","reasons","blocked_reasons"}
def validate_capability_decision_readiness_assessment(v:Any)->CapabilityDecisionReadinessAssessmentValidationResult:
 if not isinstance(v,Mapping):return CapabilityDecisionReadinessAssessmentValidationResult(False,("readiness_not_object",))
 e=[];s=v.get("decision_status")
 if set(v)!=_REQ:e.append("invalid_fields")
 if v.get("contract")!=CONTRACT or v.get("schema_version")!=SCHEMA_VERSION or s not in STATUSES or v.get("ready") is not(s=="ready"):e.append("invalid_contract_or_status")
 if v.get("execution_completion_claim") is not False or v.get("authorization_claim") is not False:e.append("forbidden_claim")
 if v.get("recommended_next_stage") not in NEXT_STAGES or not isinstance(v.get("limitations"),list):e.append("invalid_stage_or_limitations")
 if s=="ready" and (v.get("recommended_next_stage")!="bounded_decision_review" or not isinstance(v.get("readiness_checks"),Mapping) or any(v["readiness_checks"].get(n) is not True for n in ("consumer_accepted","evidence_relevant","evidence_sufficient","linkage_valid","closure_verified"))):e.append("forbidden_success_transition")
 try:f=_hash({k:x for k,x in v.items() if k not in {"decision_readiness_id","decision_readiness_fingerprint"}})
 except (TypeError,ValueError):e.append("noncanonical_value")
 else:
  if v.get("decision_readiness_fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("decision_readiness_id")!="capability-decision-readiness-assessment-"+f[:24]:e.append("id_mismatch")
 return CapabilityDecisionReadinessAssessmentValidationResult(not e,tuple(dict.fromkeys(e)))
