from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_bounded_observation_request import *
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityBoundedObservationRequestValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"contract","schema_version","observation_request_id","observation_request_fingerprint","read_only_admission_id","read_only_admission_fingerprint","authority_id","authority_fingerprint","request_id","request_fingerprint","observation_kind","relative_target","limits","request_status","accepted","reasons","blocked_reasons"}
def validate_capability_bounded_observation_request(v:Any)->CapabilityBoundedObservationRequestValidationResult:
 if not isinstance(v,Mapping):return CapabilityBoundedObservationRequestValidationResult(False,("request_not_object",))
 e=[];s=v.get("request_status");l=v.get("limits")
 if set(v)!=_REQ:e.append("invalid_fields")
 if v.get("contract")!=CONTRACT or v.get("schema_version")!=SCHEMA_VERSION:e.append("invalid_contract")
 if s not in STATUSES or v.get("accepted") is not(s=="accepted"):e.append("invalid_status")
 if s=="accepted" and (v.get("observation_kind") not in KINDS or not isinstance(l,Mapping) or set(l)!=LIMIT_FIELDS or any(not isinstance(l[n],int) or isinstance(l[n],bool) or not 0<l[n]<=HARD_LIMITS[n] for n in LIMIT_FIELDS)):e.append("forbidden_success_transition")
 try:f=_hash({k:x for k,x in v.items() if k not in {"observation_request_id","observation_request_fingerprint"}})
 except (TypeError,ValueError):e.append("noncanonical_value")
 else:
  if v.get("observation_request_fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("observation_request_id")!="capability-bounded-observation-request-"+f[:24]:e.append("id_mismatch")
 return CapabilityBoundedObservationRequestValidationResult(not e,tuple(dict.fromkeys(e)))
