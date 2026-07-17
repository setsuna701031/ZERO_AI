from dataclasses import dataclass
from datetime import datetime
from typing import Any,Mapping
from core.runtime.runtime_capability_runtime_activation_admission import *
from core.runtime.runtime_capability_runtime_activation_eligibility import _FALSE_FLAGS,_FORBIDDEN,_hash
@dataclass(frozen=True)
class CapabilityRuntimeActivationAdmissionValidationResult:valid:bool;errors:tuple[str,...]
def validate_capability_runtime_activation_admission(v:Any)->CapabilityRuntimeActivationAdmissionValidationResult:
 if not isinstance(v,Mapping):return CapabilityRuntimeActivationAdmissionValidationResult(False,("admission_not_object",))
 e=[];s=v.get("status")
 if v.get("schema")!=CAPABILITY_RUNTIME_ACTIVATION_ADMISSION_SCHEMA:e.append("invalid_schema")
 if s not in RUNTIME_ACTIVATION_ADMISSION_STATUSES:e.append("invalid_status")
 if any(v.get(n) is not(n==s) for n in RUNTIME_ACTIVATION_ADMISSION_STATUSES):e.append("inconsistent_status_flags")
 if set(v)&_FORBIDDEN:e.append("forged_execution_field")
 try:
  a=datetime.fromisoformat(v.get("admitted_at","").replace("Z","+00:00"));x=datetime.fromisoformat(v.get("admission_expires_at","").replace("Z","+00:00"));ttl=v.get("admission_ttl_seconds");assert a.tzinfo and x.tzinfo
  if isinstance(ttl,bool) or not isinstance(ttl,(int,float)) or ttl<=0 or ttl>MAXIMUM_ADMISSION_TTL_SECONDS:e.append("invalid_admission_ttl_seconds")
  elif (x-a).total_seconds()!=ttl:e.append("ttl_mismatch")
 except (ValueError,TypeError,AttributeError,AssertionError):e.append("invalid_admission_timestamp")
 if not all(isinstance(v.get(n),str) and v.get(n) for n in ("runtime_activation_preparation_id","runtime_activation_preparation_fingerprint")):e.append("missing_linkage")
 if v.get("runtime_admission_created") is not(s=="admitted") or v.get("runtime_activation_admitted") is not(s=="admitted") or any(v.get(n) is not False for n in _FALSE_FLAGS if n not in {"runtime_activation_preparation_created","runtime_admission_created"}):e.append("runtime_state_violation")
 try:
  f=_hash({a:b for a,b in v.items() if a not in {"admission_id","fingerprint"}})
  if v.get("fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("admission_id")!="capability-runtime-activation-admission-"+f[:24]:e.append("admission_id_mismatch")
 except (TypeError,ValueError):e.append("noncanonical_value")
 return CapabilityRuntimeActivationAdmissionValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["CapabilityRuntimeActivationAdmissionValidationResult","validate_capability_runtime_activation_admission"]
