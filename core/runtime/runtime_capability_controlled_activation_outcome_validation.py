from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any,Mapping
from core.runtime.runtime_capability_controlled_activation_outcome import *
from core.runtime.runtime_capability_controlled_activation_outcome import _OUTCOME_FLAGS,_evidence
from core.runtime.runtime_capability_activation_consumer_acceptance import _EXPIRIES,_LINEAGES,_FORBIDDEN,_governance_id
from core.runtime.runtime_capability_runtime_activation_eligibility import _hash
@dataclass(frozen=True)
class CapabilityControlledActivationOutcomeValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"schema","outcome_id","fingerprint","outcome",*CONTROLLED_ACTIVATION_OUTCOMES,"observed_at","consumer_id","evidence_code","prepared_at",*_EXPIRIES,"controlled_activation_preparation_id","controlled_activation_preparation_fingerprint","activation_consumer_acceptance_id","activation_consumer_acceptance_fingerprint","activation_outcome_recorded","runtime_activation_reported",*_OUTCOME_FLAGS,"reasons","errors"}|{z+s for z in _LINEAGES for s in ("_id","_fingerprint")}
def validate_capability_controlled_activation_outcome(v:Any)->CapabilityControlledActivationOutcomeValidationResult:
 if not isinstance(v,Mapping):return CapabilityControlledActivationOutcomeValidationResult(False,("outcome_not_object",))
 e=[];s=v.get("outcome")
 if set(v)!=_REQ:e.append("invalid_fields")
 if set(v)&_FORBIDDEN:e.append("forbidden_material")
 if v.get("schema")!=CAPABILITY_CONTROLLED_ACTIVATION_OUTCOME_SCHEMA:e.append("invalid_schema")
 if s not in CONTROLLED_ACTIVATION_OUTCOMES:e.append("invalid_outcome")
 if any(v.get(n) is not(n==s) for n in CONTROLLED_ACTIVATION_OUTCOMES):e.append("inconsistent_outcome_flags")
 if _governance_id(v.get("consumer_id"))!=v.get("consumer_id"):e.append("invalid_consumer_id")
 if _evidence(v.get("evidence_code"))!=v.get("evidence_code"):e.append("invalid_evidence_code")
 parsed={}
 for n in ("observed_at","prepared_at",*_EXPIRIES):
  try:p=datetime.fromisoformat(v.get(n,"").replace("Z","+00:00"));assert p.tzinfo and p.utcoffset() is not None
  except (ValueError,TypeError,AttributeError,AssertionError):e.append("invalid_"+n)
  else:parsed[n]=p
 if len(parsed)==6 and s not in {"blocked","invalid","expired"} and not(parsed["prepared_at"]<=parsed["observed_at"]<min(parsed[n] for n in _EXPIRIES)):e.append("observation_time_out_of_bounds")
 links=("controlled_activation_preparation","activation_consumer_acceptance")
 if any(not isinstance(v.get(z+x),str) or not v.get(z+x) for z in (*links,*_LINEAGES) for x in ("_id","_fingerprint")):e.append("missing_lineage")
 if v.get("activation_outcome_recorded") is not(s=="activated") or v.get("runtime_activation_reported") is not(s=="activated") or any(v.get(n) is not False for n in _OUTCOME_FLAGS):e.append("activation_state_violation")
 for n in ("reasons","errors"):
  x=v.get(n)
  if not isinstance(x,list) or x!=sorted(set(x)) or any(not isinstance(c,str) or not re.fullmatch(r"[a-z0-9_]{1,128}",c) for c in x):e.append("invalid_"+n)
 try:
  f=_hash({a:b for a,b in v.items() if a not in {"outcome_id","fingerprint"}})
  if v.get("fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("outcome_id")!="capability-controlled-activation-outcome-"+f[:24]:e.append("outcome_id_mismatch")
 except (TypeError,ValueError):e.append("noncanonical_value")
 return CapabilityControlledActivationOutcomeValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["CapabilityControlledActivationOutcomeValidationResult","validate_capability_controlled_activation_outcome"]
