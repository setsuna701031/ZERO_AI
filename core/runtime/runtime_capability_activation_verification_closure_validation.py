from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any,Mapping
from core.runtime.runtime_capability_activation_verification_closure import *
from core.runtime.runtime_capability_activation_verification_closure import _CLOSURE_FLAGS
from core.runtime.runtime_capability_activation_consumer_acceptance import _EXPIRIES,_LINEAGES,_FORBIDDEN,_governance_id
from core.runtime.runtime_capability_controlled_activation_outcome import CONTROLLED_ACTIVATION_OUTCOMES,_evidence
from core.runtime.runtime_capability_runtime_activation_eligibility import _hash
@dataclass(frozen=True)
class CapabilityActivationVerificationClosureValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"schema","closure_id","fingerprint","status",*ACTIVATION_VERIFICATION_CLOSURE_STATUSES,"verified_at","verifier_id","observed_at","consumer_id","evidence_code","reported_outcome",*_EXPIRIES,"controlled_activation_outcome_id","controlled_activation_outcome_fingerprint","controlled_activation_preparation_id","controlled_activation_preparation_fingerprint","activation_consumer_acceptance_id","activation_consumer_acceptance_fingerprint","activation_verification_completed","activation_audit_closed",*_CLOSURE_FLAGS,"reasons","errors"}|{z+s for z in _LINEAGES for s in ("_id","_fingerprint")}
def validate_capability_activation_verification_closure(v:Any)->CapabilityActivationVerificationClosureValidationResult:
 if not isinstance(v,Mapping):return CapabilityActivationVerificationClosureValidationResult(False,("closure_not_object",))
 e=[];s=v.get("status")
 if set(v)!=_REQ:e.append("invalid_fields")
 if set(v)&_FORBIDDEN:e.append("forbidden_material")
 if v.get("schema")!=CAPABILITY_ACTIVATION_VERIFICATION_CLOSURE_SCHEMA:e.append("invalid_schema")
 if s not in ACTIVATION_VERIFICATION_CLOSURE_STATUSES:e.append("invalid_status")
 if any(v.get(n) is not(n==s) for n in ACTIVATION_VERIFICATION_CLOSURE_STATUSES):e.append("inconsistent_status_flags")
 if v.get("reported_outcome") not in CONTROLLED_ACTIVATION_OUTCOMES:e.append("invalid_reported_outcome")
 if _governance_id(v.get("verifier_id"))!=v.get("verifier_id") or _governance_id(v.get("consumer_id"))!=v.get("consumer_id"):e.append("invalid_governance_identity")
 if _evidence(v.get("evidence_code"))!=v.get("evidence_code"):e.append("invalid_evidence_code")
 parsed={}
 for n in ("verified_at","observed_at",*_EXPIRIES):
  try:p=datetime.fromisoformat(v.get(n,"").replace("Z","+00:00"));assert p.tzinfo and p.utcoffset() is not None
  except (ValueError,TypeError,AttributeError,AssertionError):e.append("invalid_"+n)
  else:parsed[n]=p
 expected={"activated":"verified","not_activated":"not_verified","blocked":"blocked","failed":"failed","invalid":"invalid","expired":"expired"}.get(v.get("reported_outcome"))
 if s not in {expected,"blocked","expired"}:e.append("inconsistent_verification_mapping")
 if len(parsed)==6 and s not in {"blocked","invalid","expired"} and not(parsed["observed_at"]<=parsed["verified_at"]<min(parsed[n] for n in _EXPIRIES)):e.append("verification_time_out_of_bounds")
 links=("controlled_activation_outcome","controlled_activation_preparation","activation_consumer_acceptance")
 if any(not isinstance(v.get(z+x),str) or not v.get(z+x) for z in (*links,*_LINEAGES) for x in ("_id","_fingerprint")):e.append("missing_lineage")
 if v.get("activation_verification_completed") is not(s=="verified") or v.get("activation_audit_closed") is not(s=="verified") or any(v.get(n) is not False for n in _CLOSURE_FLAGS):e.append("activation_state_violation")
 for n in ("reasons","errors"):
  x=v.get(n)
  if not isinstance(x,list) or x!=sorted(set(x)) or any(not isinstance(c,str) or not re.fullmatch(r"[a-z0-9_]{1,128}",c) for c in x):e.append("invalid_"+n)
 try:
  f=_hash({a:b for a,b in v.items() if a not in {"closure_id","fingerprint"}})
  if v.get("fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("closure_id")!="capability-activation-verification-closure-"+f[:24]:e.append("closure_id_mismatch")
 except (TypeError,ValueError):e.append("noncanonical_value")
 return CapabilityActivationVerificationClosureValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["CapabilityActivationVerificationClosureValidationResult","validate_capability_activation_verification_closure"]
