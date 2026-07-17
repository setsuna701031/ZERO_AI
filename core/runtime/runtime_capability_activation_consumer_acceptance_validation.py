from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any,Mapping
from core.runtime.runtime_capability_activation_consumer_acceptance import *
from core.runtime.runtime_capability_activation_consumer_acceptance import _EXPIRIES,_LINEAGES,_FORBIDDEN,_SAFETY_FLAGS,_governance_id
from core.runtime.runtime_capability_runtime_activation_eligibility import _hash
@dataclass(frozen=True)
class CapabilityActivationConsumerAcceptanceValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"schema","acceptance_id","fingerprint","status",*ACTIVATION_CONSUMER_ACCEPTANCE_STATUSES,"accepted_at","consumer_id","handoff_timestamp",*_EXPIRIES,"activation_consumer_acceptance_created","activation_handoff_accepted",*_SAFETY_FLAGS,"reasons","errors"}|{z+s for z in _LINEAGES for s in ("_id","_fingerprint")}
def validate_capability_activation_consumer_acceptance(v:Any)->CapabilityActivationConsumerAcceptanceValidationResult:
 if not isinstance(v,Mapping):return CapabilityActivationConsumerAcceptanceValidationResult(False,("acceptance_not_object",))
 e=[];s=v.get("status")
 if set(v)!=_REQ:e.append("invalid_fields")
 if set(v)&_FORBIDDEN:e.append("forbidden_material")
 if v.get("schema")!=CAPABILITY_ACTIVATION_CONSUMER_ACCEPTANCE_SCHEMA:e.append("invalid_schema")
 if s not in ACTIVATION_CONSUMER_ACCEPTANCE_STATUSES:e.append("invalid_status")
 if any(v.get(n) is not(n==s) for n in ACTIVATION_CONSUMER_ACCEPTANCE_STATUSES):e.append("inconsistent_status_flags")
 if _governance_id(v.get("consumer_id"))!=v.get("consumer_id"):e.append("invalid_consumer_id")
 parsed={}
 for n in ("accepted_at","handoff_timestamp",*_EXPIRIES):
  try:p=datetime.fromisoformat(v.get(n,"").replace("Z","+00:00"));assert p.tzinfo and p.utcoffset() is not None
  except (ValueError,TypeError,AttributeError,AssertionError):e.append("invalid_"+n)
  else:parsed[n]=p
 if len(parsed)==6 and s=="accepted" and not(parsed["handoff_timestamp"]<=parsed["accepted_at"]<min(parsed[n] for n in _EXPIRIES)):e.append("acceptance_time_out_of_bounds")
 if any(not isinstance(v.get(z+x),str) or not v.get(z+x) for z in _LINEAGES for x in ("_id","_fingerprint")):e.append("missing_lineage")
 if v.get("activation_consumer_acceptance_created") is not(s=="accepted") or v.get("activation_handoff_accepted") is not(s=="accepted") or any(v.get(n) is not False for n in _SAFETY_FLAGS):e.append("activation_state_violation")
 for n in ("reasons","errors"):
  x=v.get(n)
  if not isinstance(x,list) or x!=sorted(set(x)) or any(not isinstance(c,str) or not re.fullmatch(r"[a-z0-9_]{1,128}",c) for c in x):e.append("invalid_"+n)
 try:
  f=_hash({a:b for a,b in v.items() if a not in {"acceptance_id","fingerprint"}})
  if v.get("fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("acceptance_id")!="capability-activation-consumer-acceptance-"+f[:24]:e.append("acceptance_id_mismatch")
 except (TypeError,ValueError):e.append("noncanonical_value")
 return CapabilityActivationConsumerAcceptanceValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["CapabilityActivationConsumerAcceptanceValidationResult","validate_capability_activation_consumer_acceptance"]
