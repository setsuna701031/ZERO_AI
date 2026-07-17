from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_read_only_observation_result import *
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityReadOnlyObservationResultValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"contract","schema_version","observation_result_id","observation_result_fingerprint","read_only_admission_id","read_only_admission_fingerprint","observation_request_id","observation_request_fingerprint","target_resolution_id","target_resolution_fingerprint","observation_kind","result_status","observed","observation","evidence_descriptor","bytes_read","entries_observed","truncated","side_effects_performed","reasons","blocked_reasons","failure_reasons"}
def validate_capability_read_only_observation_result(v:Any)->CapabilityReadOnlyObservationResultValidationResult:
 if not isinstance(v,Mapping):return CapabilityReadOnlyObservationResultValidationResult(False,("result_not_object",))
 e=[];s=v.get("result_status")
 if set(v)!=_REQ:e.append("invalid_fields")
 if v.get("contract")!=CONTRACT or v.get("schema_version")!=SCHEMA_VERSION or s not in STATUSES or v.get("observed") is not(s=="observed"):e.append("invalid_contract_or_status")
 if v.get("side_effects_performed")!=[]:e.append("side_effect_invariant_violation")
 for n in ("bytes_read","entries_observed"):
  if not isinstance(v.get(n),int) or isinstance(v.get(n),bool) or v[n]<0:e.append("invalid_counter")
 try:f=_hash({k:x for k,x in v.items() if k not in {"observation_result_id","observation_result_fingerprint"}})
 except (TypeError,ValueError):e.append("noncanonical_value")
 else:
  if v.get("observation_result_fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("observation_result_id")!="capability-read-only-observation-result-"+f[:24]:e.append("id_mismatch")
 return CapabilityReadOnlyObservationResultValidationResult(not e,tuple(dict.fromkeys(e)))
