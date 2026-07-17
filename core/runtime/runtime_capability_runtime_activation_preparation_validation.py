from dataclasses import dataclass
from datetime import datetime
from typing import Any,Mapping
from core.runtime.runtime_capability_runtime_activation_preparation import *
from core.runtime.runtime_capability_runtime_activation_eligibility import _FALSE_FLAGS,_FORBIDDEN,_hash
@dataclass(frozen=True)
class CapabilityRuntimeActivationPreparationValidationResult:valid:bool;errors:tuple[str,...]
def validate_capability_runtime_activation_preparation(v:Any)->CapabilityRuntimeActivationPreparationValidationResult:
 if not isinstance(v,Mapping):return CapabilityRuntimeActivationPreparationValidationResult(False,("preparation_not_object",))
 e=[];s=v.get("status")
 if v.get("schema")!=CAPABILITY_RUNTIME_ACTIVATION_PREPARATION_SCHEMA:e.append("invalid_schema")
 if s not in RUNTIME_ACTIVATION_PREPARATION_STATUSES:e.append("invalid_status")
 if any(v.get(n) is not(n==s) for n in RUNTIME_ACTIVATION_PREPARATION_STATUSES):e.append("inconsistent_status_flags")
 if set(v)&_FORBIDDEN:e.append("forged_execution_field")
 for n in ("prepared_at","evaluated_at","token_handed_off_at","issued_at","issuance_expires_at","token_created_at","token_expires_at","authorized_at","authorization_expires_at"):
  try:p=datetime.fromisoformat(v.get(n,"").replace("Z","+00:00"));assert p.tzinfo is not None and p.utcoffset() is not None
  except (ValueError,TypeError,AttributeError,AssertionError):e.append("invalid_"+n)
 if not all(isinstance(v.get(n),str) and v.get(n) for n in ("runtime_activation_eligibility_id","runtime_activation_eligibility_fingerprint")):e.append("missing_linkage")
 if v.get("runtime_activation_preparation_created") is not(s=="prepared") or any(v.get(n) is not False for n in _FALSE_FLAGS if n!="runtime_activation_preparation_created"):e.append("runtime_state_violation")
 try:
  f=_hash({a:b for a,b in v.items() if a not in {"preparation_id","fingerprint"}})
  if v.get("fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("preparation_id")!="capability-runtime-activation-preparation-"+f[:24]:e.append("preparation_id_mismatch")
 except (TypeError,ValueError):e.append("noncanonical_value")
 return CapabilityRuntimeActivationPreparationValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["CapabilityRuntimeActivationPreparationValidationResult","validate_capability_runtime_activation_preparation"]
