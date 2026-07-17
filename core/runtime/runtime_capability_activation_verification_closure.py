from __future__ import annotations
from typing import Any,Mapping
from core.runtime.runtime_capability_activation_consumer_acceptance import _EXPIRIES,_LINEAGES,_FORBIDDEN,_governance_id,_time,_text,_identity
from core.runtime.runtime_capability_controlled_activation_outcome import _OUTCOME_FLAGS
CAPABILITY_ACTIVATION_VERIFICATION_CLOSURE_SCHEMA="zero.runtime.capability_activation_verification_closure.v1"
ACTIVATION_VERIFICATION_CLOSURE_STATUSES=frozenset({"verified","not_verified","blocked","failed","invalid","expired"})
_CLOSURE_FLAGS=("runtime_process_started_by_contract","executor_admitted","execution_session_created","execution_authority_granted","mutation_authority_granted")
def close_capability_activation_verification(controlled_activation_outcome:Any,*,verified_at:Any=None,verifier_id:Any=None)->dict[str,Any]:
 u=dict(controlled_activation_outcome) if isinstance(controlled_activation_outcome,Mapping) else {};vt,v=_time(verified_at,True);verifier=_governance_id(verifier_id);reasons=[];errors=[];status="invalid"
 from core.runtime.runtime_capability_controlled_activation_outcome_validation import validate_capability_controlled_activation_outcome
 valid=validate_capability_controlled_activation_outcome(u)
 if v is None:errors.append("invalid_verified_at")
 if verifier is None:errors.append("invalid_verifier_id")
 forged=bool(set(u)&_FORBIDDEN) or any(n in u and u.get(n) is not False for n in _OUTCOME_FLAGS)
 if forged:status="blocked";reasons.append("authority_flag_violation");errors.append("activation_state_violation")
 elif not valid.valid:reasons.append("controlled_activation_outcome_invalid");errors.append("invalid_controlled_activation_outcome")
 elif errors:status="blocked";reasons.append("verification_governance_blocked")
 else:
  _,o=_time(u.get("observed_at"));limits=[_time(u.get(n))[1] for n in _EXPIRIES];s=u["outcome"]
  if s=="activated":status="verified"
  elif s=="not_activated":status="not_verified"
  else:status=s
  if v<o:status="blocked";reasons.append("verification_not_yet_effective")
  elif v>=min(limits):status="expired";reasons.append("activation_verification_expired")
  else:reasons.append("activation_outcome_"+status)
 base={"schema":CAPABILITY_ACTIVATION_VERIFICATION_CLOSURE_SCHEMA,"status":status,**{n:n==status for n in ACTIVATION_VERIFICATION_CLOSURE_STATUSES},"verified_at":vt or "1970-01-01T00:00:00Z","verifier_id":verifier or "unavailable","observed_at":_time(u.get("observed_at"))[0] or "1970-01-01T00:00:00Z","consumer_id":_text(u.get("consumer_id")),"evidence_code":_text(u.get("evidence_code")),"reported_outcome":_text(u.get("outcome")),**{n:_time(u.get(n))[0] or "1970-01-01T00:00:01Z" for n in _EXPIRIES},"controlled_activation_outcome_id":_text(u.get("outcome_id")),"controlled_activation_outcome_fingerprint":_text(u.get("fingerprint")),"controlled_activation_preparation_id":_text(u.get("controlled_activation_preparation_id")),"controlled_activation_preparation_fingerprint":_text(u.get("controlled_activation_preparation_fingerprint")),"activation_consumer_acceptance_id":_text(u.get("activation_consumer_acceptance_id")),"activation_consumer_acceptance_fingerprint":_text(u.get("activation_consumer_acceptance_fingerprint")),"activation_verification_completed":status=="verified","activation_audit_closed":status=="verified",**{n:False for n in _CLOSURE_FLAGS},"reasons":sorted(set(reasons)),"errors":sorted(set(errors))}
 for z in _LINEAGES:base[z+"_id"]=_text(u.get(z+"_id"));base[z+"_fingerprint"]=_text(u.get(z+"_fingerprint"))
 r=_identity(base,"closure","capability-activation-verification-closure-")
 from core.runtime.runtime_capability_activation_verification_closure_validation import validate_capability_activation_verification_closure
 if not validate_capability_activation_verification_closure(r).valid:raise RuntimeError("internal activation verification closure validation failed")
 return r
__all__=["CAPABILITY_ACTIVATION_VERIFICATION_CLOSURE_SCHEMA","ACTIVATION_VERIFICATION_CLOSURE_STATUSES","close_capability_activation_verification"]
