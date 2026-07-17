from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_observation_evidence_consumer_acceptance import *
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityObservationEvidenceConsumerAcceptanceValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"contract","schema_version","consumer_acceptance_id","consumer_acceptance_fingerprint","observation_closure_id","observation_closure_fingerprint","authority_id","authority_fingerprint","execution_request_id","execution_request_fingerprint","bridge_closure_id","bridge_closure_fingerprint","observation_request_id","observation_request_fingerprint","observation_result_id","observation_result_fingerprint","observation_kind","acceptance_status","accepted","reasons","blocked_reasons"}
def validate_capability_observation_evidence_consumer_acceptance(v:Any)->CapabilityObservationEvidenceConsumerAcceptanceValidationResult:
 if not isinstance(v,Mapping):return CapabilityObservationEvidenceConsumerAcceptanceValidationResult(False,("acceptance_not_object",))
 e=[];s=v.get("acceptance_status")
 if set(v)!=_REQ:e.append("invalid_fields")
 if v.get("contract")!=CONTRACT or v.get("schema_version")!=SCHEMA_VERSION or s not in STATUSES or v.get("accepted") is not(s=="accepted"):e.append("invalid_contract_or_status")
 if s=="accepted" and (v.get("observation_kind") not in KINDS or any(not isinstance(v.get(n),str) or not v.get(n) for n in _REQ if n.endswith("_id") or n.endswith("_fingerprint"))):e.append("forbidden_success_transition")
 try:f=_hash({k:x for k,x in v.items() if k not in {"consumer_acceptance_id","consumer_acceptance_fingerprint"}})
 except (TypeError,ValueError):e.append("noncanonical_value")
 else:
  if v.get("consumer_acceptance_fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("consumer_acceptance_id")!="capability-observation-evidence-consumer-acceptance-"+f[:24]:e.append("id_mismatch")
 return CapabilityObservationEvidenceConsumerAcceptanceValidationResult(not e,tuple(dict.fromkeys(e)))
