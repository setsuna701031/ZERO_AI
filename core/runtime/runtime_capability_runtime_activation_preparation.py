from __future__ import annotations
from typing import Any,Mapping
from core.runtime.runtime_capability_runtime_activation_eligibility import _UPSTREAM,_FALSE_FLAGS,_FORBIDDEN,_time,_text,_identity
CAPABILITY_RUNTIME_ACTIVATION_PREPARATION_SCHEMA="zero.runtime.capability_runtime_activation_preparation.v1"
RUNTIME_ACTIVATION_PREPARATION_STATUSES=frozenset({"prepared","not_prepared","blocked","invalid","expired"})
def prepare_capability_runtime_activation(runtime_activation_eligibility:Any,*,prepared_at:Any=None)->dict[str,Any]:
 u=dict(runtime_activation_eligibility) if isinstance(runtime_activation_eligibility,Mapping) else {};pt,p=_time(prepared_at,True);reasons=[];errors=[];status="invalid"
 from core.runtime.runtime_capability_runtime_activation_eligibility_validation import validate_capability_runtime_activation_eligibility
 valid=validate_capability_runtime_activation_eligibility(u);forged=bool(set(u)&_FORBIDDEN) or any(u.get(n) is not False for n in _FALSE_FLAGS if n in u)
 if p is None:errors.append("invalid_prepared_at")
 if forged:status="blocked";reasons.append("authority_flag_violation");errors.append("runtime_state_violation")
 elif not valid.valid:reasons.append("runtime_activation_eligibility_invalid");errors.append("invalid_runtime_activation_eligibility")
 else:
  _,e=_time(u.get("evaluated_at"));_,ie=_time(u.get("issuance_expires_at"));_,te=_time(u.get("token_expires_at"));_,ae=_time(u.get("authorization_expires_at"));s=u["status"]
  if s=="ineligible":status="not_prepared";reasons.append("runtime_activation_ineligible")
  elif s in {"blocked","invalid","expired"}:status=s;reasons.append("runtime_activation_eligibility_"+s)
  elif p<e:status="blocked";reasons.append("preparation_not_yet_effective")
  elif p>=min(ie,te,ae):status="expired";reasons.append("authorization_lifetime_expired")
  else:status="prepared";reasons.append("runtime_activation_prepared")
 base={k:v for k,v in u.items() if k not in {"schema","eligibility_id","fingerprint","status",*RUNTIME_ACTIVATION_PREPARATION_STATUSES,"runtime_activation_eligibility_confirmed","reasons","errors"}}
 base.update({"schema":CAPABILITY_RUNTIME_ACTIVATION_PREPARATION_SCHEMA,"status":status,**{n:n==status for n in RUNTIME_ACTIVATION_PREPARATION_STATUSES},"prepared_at":pt or "1970-01-01T00:00:00Z","runtime_activation_eligibility_id":_text(u.get("eligibility_id")),"runtime_activation_eligibility_fingerprint":_text(u.get("fingerprint")),"runtime_activation_eligibility_status":_text(u.get("status")),"runtime_activation_preparation_created":status=="prepared",**{n:False for n in _FALSE_FLAGS if n!="runtime_activation_preparation_created"},"reasons":sorted(set(reasons)),"errors":sorted(set(errors))})
 r=_identity(base,"preparation","capability-runtime-activation-preparation-")
 from core.runtime.runtime_capability_runtime_activation_preparation_validation import validate_capability_runtime_activation_preparation
 if not validate_capability_runtime_activation_preparation(r).valid:raise RuntimeError("internal preparation validation failed")
 return r
__all__=["CAPABILITY_RUNTIME_ACTIVATION_PREPARATION_SCHEMA","RUNTIME_ACTIVATION_PREPARATION_STATUSES","prepare_capability_runtime_activation"]
