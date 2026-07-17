from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any,Mapping
from core.runtime.runtime_capability_controlled_activation_preparation import *
from core.runtime.runtime_capability_controlled_activation_preparation import _PREP_FLAGS
from core.runtime.runtime_capability_activation_consumer_acceptance import _EXPIRIES,_LINEAGES,_FORBIDDEN,_governance_id
from core.runtime.runtime_capability_runtime_activation_eligibility import _hash
@dataclass(frozen=True)
class CapabilityControlledActivationPreparationValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"schema","preparation_id","fingerprint","status",*CONTROLLED_ACTIVATION_PREPARATION_STATUSES,"prepared_at","consumer_id","accepted_at",*_EXPIRIES,"activation_consumer_acceptance_id","activation_consumer_acceptance_fingerprint","controlled_activation_preparation_created",*_PREP_FLAGS,"reasons","errors"}|{z+s for z in _LINEAGES for s in ("_id","_fingerprint")}
def validate_capability_controlled_activation_preparation(v:Any)->CapabilityControlledActivationPreparationValidationResult:
 if not isinstance(v,Mapping):return CapabilityControlledActivationPreparationValidationResult(False,("preparation_not_object",))
 e=[];s=v.get("status")
 if set(v)!=_REQ:e.append("invalid_fields")
 if set(v)&_FORBIDDEN:e.append("forbidden_material")
 if v.get("schema")!=CAPABILITY_CONTROLLED_ACTIVATION_PREPARATION_SCHEMA:e.append("invalid_schema")
 if s not in CONTROLLED_ACTIVATION_PREPARATION_STATUSES:e.append("invalid_status")
 if any(v.get(n) is not(n==s) for n in CONTROLLED_ACTIVATION_PREPARATION_STATUSES):e.append("inconsistent_status_flags")
 if _governance_id(v.get("consumer_id"))!=v.get("consumer_id"):e.append("invalid_consumer_id")
 parsed={}
 for n in ("prepared_at","accepted_at",*_EXPIRIES):
  try:p=datetime.fromisoformat(v.get(n,"").replace("Z","+00:00"));assert p.tzinfo and p.utcoffset() is not None
  except (ValueError,TypeError,AttributeError,AssertionError):e.append("invalid_"+n)
  else:parsed[n]=p
 if len(parsed)==6 and s=="prepared" and not(parsed["accepted_at"]<=parsed["prepared_at"]<min(parsed[n] for n in _EXPIRIES)):e.append("preparation_time_out_of_bounds")
 if any(not isinstance(v.get(n),str) or not v.get(n) for n in ("activation_consumer_acceptance_id","activation_consumer_acceptance_fingerprint")) or any(not isinstance(v.get(z+x),str) or not v.get(z+x) for z in _LINEAGES for x in ("_id","_fingerprint")):e.append("missing_lineage")
 if v.get("controlled_activation_preparation_created") is not(s=="prepared") or any(v.get(n) is not False for n in _PREP_FLAGS):e.append("activation_state_violation")
 for n in ("reasons","errors"):
  x=v.get(n)
  if not isinstance(x,list) or x!=sorted(set(x)) or any(not isinstance(c,str) or not re.fullmatch(r"[a-z0-9_]{1,128}",c) for c in x):e.append("invalid_"+n)
 try:
  f=_hash({a:b for a,b in v.items() if a not in {"preparation_id","fingerprint"}})
  if v.get("fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("preparation_id")!="capability-controlled-activation-preparation-"+f[:24]:e.append("preparation_id_mismatch")
 except (TypeError,ValueError):e.append("noncanonical_value")
 return CapabilityControlledActivationPreparationValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["CapabilityControlledActivationPreparationValidationResult","validate_capability_controlled_activation_preparation"]
