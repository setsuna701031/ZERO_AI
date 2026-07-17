from __future__ import annotations
from typing import Any,Mapping
from core.runtime.runtime_capability_activation_consumer_acceptance import _EXPIRIES,_LINEAGES,_FORBIDDEN,_SAFETY_FLAGS,_time,_text,_identity,_bad_flags
CAPABILITY_CONTROLLED_ACTIVATION_PREPARATION_SCHEMA="zero.runtime.capability_controlled_activation_preparation.v1"
CONTROLLED_ACTIVATION_PREPARATION_STATUSES=frozenset({"prepared","not_prepared","blocked","invalid","expired"})
_PREP_FLAGS=("activation_command_created","activation_attempted","activation_outcome_recorded","runtime_process_started","runtime_activated","executor_admitted","execution_session_created","execution_authority_granted")
def prepare_capability_controlled_activation(activation_consumer_acceptance:Any,*,prepared_at:Any=None)->dict[str,Any]:
 u=dict(activation_consumer_acceptance) if isinstance(activation_consumer_acceptance,Mapping) else {};pt,p=_time(prepared_at,True);reasons=[];errors=[];status="invalid"
 from core.runtime.runtime_capability_activation_consumer_acceptance_validation import validate_capability_activation_consumer_acceptance
 valid=validate_capability_activation_consumer_acceptance(u)
 if p is None:errors.append("invalid_prepared_at")
 if _bad_flags(u):status="blocked";reasons.append("authority_flag_violation");errors.append("activation_state_violation")
 elif not valid.valid:reasons.append("activation_consumer_acceptance_invalid");errors.append("invalid_activation_consumer_acceptance")
 elif errors:status="blocked";reasons.append("preparation_policy_blocked")
 else:
  _,a=_time(u.get("accepted_at"));limits=[_time(u.get(n))[1] for n in _EXPIRIES];s=u["status"]
  if s=="not_accepted":status="not_prepared";reasons.append("activation_handoff_not_accepted")
  elif s in {"blocked","invalid","expired"}:status=s;reasons.append("activation_acceptance_"+s)
  elif p<a:status="blocked";reasons.append("preparation_not_yet_effective")
  elif p>=min(limits):status="expired";reasons.append("activation_admission_expired")
  else:status="prepared";reasons.append("controlled_activation_prepared")
 base={"schema":CAPABILITY_CONTROLLED_ACTIVATION_PREPARATION_SCHEMA,"status":status,**{n:n==status for n in CONTROLLED_ACTIVATION_PREPARATION_STATUSES},"prepared_at":pt or "1970-01-01T00:00:00Z","consumer_id":_text(u.get("consumer_id")),"accepted_at":_time(u.get("accepted_at"))[0] or "1970-01-01T00:00:00Z",**{n:_time(u.get(n))[0] or "1970-01-01T00:00:01Z" for n in _EXPIRIES},"activation_consumer_acceptance_id":_text(u.get("acceptance_id")),"activation_consumer_acceptance_fingerprint":_text(u.get("fingerprint")),"controlled_activation_preparation_created":status=="prepared",**{n:False for n in _PREP_FLAGS},"reasons":sorted(set(reasons)),"errors":sorted(set(errors))}
 for z in _LINEAGES:base[z+"_id"]=_text(u.get(z+"_id"));base[z+"_fingerprint"]=_text(u.get(z+"_fingerprint"))
 r=_identity(base,"preparation","capability-controlled-activation-preparation-")
 from core.runtime.runtime_capability_controlled_activation_preparation_validation import validate_capability_controlled_activation_preparation
 if not validate_capability_controlled_activation_preparation(r).valid:raise RuntimeError("internal controlled activation preparation validation failed")
 return r
__all__=["CAPABILITY_CONTROLLED_ACTIVATION_PREPARATION_SCHEMA","CONTROLLED_ACTIVATION_PREPARATION_STATUSES","prepare_capability_controlled_activation"]
