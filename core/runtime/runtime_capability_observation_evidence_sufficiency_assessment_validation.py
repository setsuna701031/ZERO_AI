from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_observation_evidence_sufficiency_assessment import *
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityObservationEvidenceSufficiencyAssessmentValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"contract","schema_version","sufficiency_assessment_id","sufficiency_assessment_fingerprint","relevance_assessment_id","relevance_assessment_fingerprint","consumer_acceptance_id","consumer_acceptance_fingerprint","observation_closure_id","observation_closure_fingerprint","observation_result_id","observation_result_fingerprint","decision_question","sufficiency_requirements","evidence_characteristics","sufficiency_status","sufficient","limitations","reasons","blocked_reasons"}
def validate_capability_observation_evidence_sufficiency_assessment(v:Any)->CapabilityObservationEvidenceSufficiencyAssessmentValidationResult:
 if not isinstance(v,Mapping):return CapabilityObservationEvidenceSufficiencyAssessmentValidationResult(False,("sufficiency_not_object",))
 e=[];s=v.get("sufficiency_status");req=v.get("sufficiency_requirements")
 if set(v)!=_REQ:e.append("invalid_fields")
 if v.get("contract")!=CONTRACT or v.get("schema_version")!=SCHEMA_VERSION or s not in STATUSES or v.get("sufficient") is not(s=="sufficient"):e.append("invalid_contract_or_status")
 if not isinstance(req,Mapping) or set(req)!=REQUIREMENT_FIELDS or any(not isinstance(req.get(n),bool) for n in REQUIREMENT_FIELDS):e.append("invalid_requirements")
 if not isinstance(v.get("limitations"),list) or any(not isinstance(x,str) or not x for x in v.get("limitations",[])) or not isinstance(v.get("evidence_characteristics"),Mapping):e.append("malformed_evidence_characteristics")
 if s=="sufficient" and req.get("require_not_truncated") is True and v.get("evidence_characteristics",{}).get("truncated") is True:e.append("truncated_evidence_claimed_sufficient")
 try:f=_hash({k:x for k,x in v.items() if k not in {"sufficiency_assessment_id","sufficiency_assessment_fingerprint"}})
 except (TypeError,ValueError):e.append("noncanonical_value")
 else:
  if v.get("sufficiency_assessment_fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("sufficiency_assessment_id")!="capability-observation-evidence-sufficiency-assessment-"+f[:24]:e.append("id_mismatch")
 return CapabilityObservationEvidenceSufficiencyAssessmentValidationResult(not e,tuple(dict.fromkeys(e)))
