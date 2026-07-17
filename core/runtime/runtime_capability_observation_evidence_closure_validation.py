from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_observation_evidence_closure import *
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityObservationEvidenceClosureValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"contract","schema_version","observation_closure_id","observation_closure_fingerprint","authority_id","authority_fingerprint","request_id","request_fingerprint","bridge_closure_id","bridge_closure_fingerprint","read_only_admission_id","read_only_admission_fingerprint","observation_request_id","observation_request_fingerprint","target_resolution_id","target_resolution_fingerprint","observation_result_id","observation_result_fingerprint","chain_validation_results","containment_validation_results","read_only_invariant_results","boundedness_validation_results","evidence_validation_results","execution_completion_claim","recommended_v1_2_outcome_status","verification_status","closed","reasons","blocked_reasons","failure_reasons"}
def validate_capability_observation_evidence_closure(v:Any)->CapabilityObservationEvidenceClosureValidationResult:
 if not isinstance(v,Mapping):return CapabilityObservationEvidenceClosureValidationResult(False,("closure_not_object",))
 e=[];s=v.get("verification_status")
 if set(v)!=_REQ:e.append("invalid_fields")
 if v.get("contract")!=CONTRACT or v.get("schema_version")!=SCHEMA_VERSION or s not in STATUSES or v.get("closed") is not(s=="verified_closed"):e.append("invalid_contract_or_status")
 if v.get("execution_completion_claim") is not False:e.append("completion_claim_forbidden")
 if s=="verified_closed" and (v.get("recommended_v1_2_outcome_status")!="not_completed" or any(not isinstance(v.get(n),Mapping) or v[n].get("valid") is not True for n in ("chain_validation_results","containment_validation_results","read_only_invariant_results","boundedness_validation_results","evidence_validation_results"))):e.append("forbidden_success_transition")
 try:f=_hash({k:x for k,x in v.items() if k not in {"observation_closure_id","observation_closure_fingerprint"}})
 except (TypeError,ValueError):e.append("noncanonical_value")
 else:
  if v.get("observation_closure_fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("observation_closure_id")!="capability-observation-evidence-closure-"+f[:24]:e.append("id_mismatch")
 return CapabilityObservationEvidenceClosureValidationResult(not e,tuple(dict.fromkeys(e)))
