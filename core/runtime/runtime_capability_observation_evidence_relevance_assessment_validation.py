from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_observation_evidence_relevance_assessment import *
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityObservationEvidenceRelevanceAssessmentValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"contract","schema_version","relevance_assessment_id","relevance_assessment_fingerprint","consumer_acceptance_id","consumer_acceptance_fingerprint","observation_closure_id","observation_closure_fingerprint","observation_result_id","observation_result_fingerprint","decision_question","decision_scope","required_observation_kinds","observed_kind","target_reference","relevance_rules","relevance_status","relevant","reasons","blocked_reasons"}
def validate_capability_observation_evidence_relevance_assessment(v:Any)->CapabilityObservationEvidenceRelevanceAssessmentValidationResult:
 if not isinstance(v,Mapping):return CapabilityObservationEvidenceRelevanceAssessmentValidationResult(False,("relevance_not_object",))
 e=[];s=v.get("relevance_status");q=v.get("decision_question")
 if set(v)!=_REQ:e.append("invalid_fields")
 if v.get("contract")!=CONTRACT or v.get("schema_version")!=SCHEMA_VERSION or s not in STATUSES or v.get("relevant") is not(s=="relevant"):e.append("invalid_contract_or_status")
 if not isinstance(q,Mapping) or set(q)!=QUESTION_FIELDS or q.get("decision_scope")!=v.get("decision_scope") or q.get("required_observation_kinds")!=v.get("required_observation_kinds") or q.get("target_reference")!=v.get("target_reference"):e.append("decision_question_mismatch")
 expected=RULES.get(q.get("question_type")) if isinstance(q,Mapping) else None
 if s=="relevant" and (expected not in {"*",v.get("observed_kind")} or v.get("observed_kind") not in v.get("required_observation_kinds",[])):e.append("relevance_rule_mismatch")
 try:f=_hash({k:x for k,x in v.items() if k not in {"relevance_assessment_id","relevance_assessment_fingerprint"}})
 except (TypeError,ValueError):e.append("noncanonical_value")
 else:
  if v.get("relevance_assessment_fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("relevance_assessment_id")!="capability-observation-evidence-relevance-assessment-"+f[:24]:e.append("id_mismatch")
 return CapabilityObservationEvidenceRelevanceAssessmentValidationResult(not e,tuple(dict.fromkeys(e)))
