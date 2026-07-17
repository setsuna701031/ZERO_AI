from dataclasses import dataclass
from datetime import datetime
from typing import Any,Mapping
from core.runtime.runtime_capability_runtime_activation_admission_handoff import *
from core.runtime.runtime_capability_runtime_activation_admission_handoff import _recipient
from core.runtime.runtime_capability_runtime_activation_eligibility import _FALSE_FLAGS,_FORBIDDEN,_hash
@dataclass(frozen=True)
class CapabilityRuntimeActivationAdmissionHandoffValidationResult:valid:bool;errors:tuple[str,...]
def validate_capability_runtime_activation_admission_handoff(v:Any)->CapabilityRuntimeActivationAdmissionHandoffValidationResult:
 if not isinstance(v,Mapping):return CapabilityRuntimeActivationAdmissionHandoffValidationResult(False,("handoff_not_object",))
 e=[];s=v.get("status")
 if v.get("schema")!=CAPABILITY_RUNTIME_ACTIVATION_ADMISSION_HANDOFF_SCHEMA:e.append("invalid_schema")
 if s not in RUNTIME_ACTIVATION_ADMISSION_HANDOFF_STATUSES:e.append("invalid_status")
 if any(v.get(n) is not(n==s) for n in RUNTIME_ACTIVATION_ADMISSION_HANDOFF_STATUSES):e.append("inconsistent_status_flags")
 if set(v)&_FORBIDDEN:e.append("forged_transport_field")
 if _recipient(v.get("recipient_id"))!=v.get("recipient_id"):e.append("invalid_recipient_id")
 try:p=datetime.fromisoformat(v.get("handed_off_at","").replace("Z","+00:00"));assert p.tzinfo and p.utcoffset() is not None
 except (ValueError,TypeError,AttributeError,AssertionError):e.append("invalid_handed_off_at")
 if not all(isinstance(v.get(n),str) and v.get(n) for n in ("runtime_activation_admission_id","runtime_activation_admission_fingerprint")):e.append("missing_linkage")
 if v.get("runtime_admission_handoff_created") is not(s=="handed_off") or v.get("runtime_admission_handed_off") is not(s=="handed_off") or v.get("handoff_delivered") is not False or v.get("handoff_acknowledged") is not False or any(v.get(n) is not False for n in _FALSE_FLAGS if n not in {"runtime_activation_preparation_created","runtime_admission_created"}):e.append("runtime_state_violation")
 try:
  f=_hash({a:b for a,b in v.items() if a not in {"handoff_id","fingerprint"}})
  if v.get("fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("handoff_id")!="capability-runtime-activation-admission-handoff-"+f[:24]:e.append("handoff_id_mismatch")
 except (TypeError,ValueError):e.append("noncanonical_value")
 return CapabilityRuntimeActivationAdmissionHandoffValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["CapabilityRuntimeActivationAdmissionHandoffValidationResult","validate_capability_runtime_activation_admission_handoff"]
