from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any,Mapping
from core.runtime.runtime_capability_runtime_activation_eligibility import *
from core.runtime.runtime_capability_runtime_activation_eligibility import _UPSTREAM,_FALSE_FLAGS,_FORBIDDEN,_hash
@dataclass(frozen=True)
class CapabilityRuntimeActivationEligibilityValidationResult:valid:bool;errors:tuple[str,...]
def validate_capability_runtime_activation_eligibility(v:Any)->CapabilityRuntimeActivationEligibilityValidationResult:
 if not isinstance(v,Mapping):return CapabilityRuntimeActivationEligibilityValidationResult(False,("eligibility_not_object",))
 req={"schema","eligibility_id","fingerprint","status",*RUNTIME_ACTIVATION_ELIGIBILITY_STATUSES,"evaluated_at","token_handed_off_at","recipient_id","issued_at","issuance_expires_at","token_created_at","token_expires_at","authorized_at","authorization_expires_at","runtime_activation_eligibility_confirmed",*_FALSE_FLAGS,"reasons","errors"}|{z+s for z in _UPSTREAM for s in ("_id","_fingerprint")};e=[];s=v.get("status")
 if set(v)!=req:e.append("invalid_fields")
 if set(v)&_FORBIDDEN:e.append("forged_execution_field")
 if v.get("schema")!=CAPABILITY_RUNTIME_ACTIVATION_ELIGIBILITY_SCHEMA:e.append("invalid_schema")
 if s not in RUNTIME_ACTIVATION_ELIGIBILITY_STATUSES:e.append("invalid_status")
 if any(v.get(n) is not(n==s) for n in RUNTIME_ACTIVATION_ELIGIBILITY_STATUSES):e.append("inconsistent_status_flags")
 for n in ("evaluated_at","token_handed_off_at","issued_at","issuance_expires_at","token_created_at","token_expires_at","authorized_at","authorization_expires_at"):
  try:p=datetime.fromisoformat(v.get(n,"").replace("Z","+00:00"));assert p.tzinfo is not None and p.utcoffset() is not None
  except (ValueError,TypeError,AttributeError,AssertionError):e.append("invalid_"+n)
 if any(not isinstance(v.get(z+s),str) or not v.get(z+s) for z in _UPSTREAM for s in ("_id","_fingerprint")):e.append("missing_linkage")
 if v.get("runtime_activation_eligibility_confirmed") is not(s=="eligible") or any(v.get(n) is not False for n in _FALSE_FLAGS):e.append("runtime_state_violation")
 for n in ("reasons","errors"):
  x=v.get(n)
  if not isinstance(x,list) or x!=sorted(set(x)) or any(not isinstance(c,str) or not re.fullmatch(r"[a-z0-9_]{1,128}",c) for c in x):e.append("invalid_"+n)
 try:
  f=_hash({a:b for a,b in v.items() if a not in {"eligibility_id","fingerprint"}})
  if v.get("fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("eligibility_id")!="capability-runtime-activation-eligibility-"+f[:24]:e.append("eligibility_id_mismatch")
 except (TypeError,ValueError):e.append("noncanonical_value")
 return CapabilityRuntimeActivationEligibilityValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["CapabilityRuntimeActivationEligibilityValidationResult","validate_capability_runtime_activation_eligibility"]
