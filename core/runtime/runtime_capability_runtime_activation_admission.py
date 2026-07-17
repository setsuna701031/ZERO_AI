from __future__ import annotations
from datetime import timedelta
from typing import Any,Mapping
from core.runtime.runtime_capability_runtime_activation_eligibility import _FALSE_FLAGS,_FORBIDDEN,_time,_text,_identity
CAPABILITY_RUNTIME_ACTIVATION_ADMISSION_SCHEMA="zero.runtime.capability_runtime_activation_admission.v1"
RUNTIME_ACTIVATION_ADMISSION_STATUSES=frozenset({"admitted","not_admitted","blocked","invalid","expired"})
DEFAULT_ADMISSION_TTL_SECONDS=30
MAXIMUM_ADMISSION_TTL_SECONDS=60
def admit_capability_runtime_activation(runtime_activation_preparation:Any,*,admitted_at:Any=None,admission_expires_at:Any=None,admission_ttl_seconds:Any=None)->dict[str,Any]:
 u=dict(runtime_activation_preparation) if isinstance(runtime_activation_preparation,Mapping) else {};at,a=_time(admitted_at,True);xt,x=_time(admission_expires_at);reasons=[];errors=[];status="invalid";ttl=None
 from core.runtime.runtime_capability_runtime_activation_preparation_validation import validate_capability_runtime_activation_preparation
 valid=validate_capability_runtime_activation_preparation(u);forged=bool(set(u)&_FORBIDDEN) or any(u.get(n) is not False for n in _FALSE_FLAGS if n in u and n!="runtime_activation_preparation_created")
 if a is None:errors.append("invalid_admitted_at")
 if admission_ttl_seconds is not None and (isinstance(admission_ttl_seconds,bool) or not isinstance(admission_ttl_seconds,int) or not 0<admission_ttl_seconds<=MAXIMUM_ADMISSION_TTL_SECONDS):errors.append("invalid_admission_ttl_seconds")
 else:ttl=admission_ttl_seconds
 if a is not None and x is None:
  ttl=DEFAULT_ADMISSION_TTL_SECONDS if ttl is None else ttl;x=a+timedelta(seconds=ttl);xt=x.isoformat().replace("+00:00","Z")
 elif a is not None and x is not None:
  delta=(x-a).total_seconds()
  if delta<=0 or delta>MAXIMUM_ADMISSION_TTL_SECONDS:errors.append("invalid_admission_expiry")
  if ttl is not None and delta!=ttl:errors.append("ttl_mismatch")
  ttl=int(delta) if delta.is_integer() else delta
 if forged:status="blocked";reasons.append("authority_flag_violation");errors.append("runtime_state_violation")
 elif not valid.valid:reasons.append("runtime_activation_preparation_invalid");errors.append("invalid_runtime_activation_preparation")
 elif errors:status="blocked";reasons.append("admission_policy_blocked")
 else:
  _,p=_time(u.get("prepared_at"));limits=[_time(u.get(n))[1] for n in ("issuance_expires_at","token_expires_at","authorization_expires_at")];s=u["status"]
  if s=="not_prepared":status="not_admitted";reasons.append("runtime_activation_not_prepared")
  elif s in {"blocked","invalid","expired"}:status=s;reasons.append("runtime_activation_preparation_"+s)
  elif a<p:status="blocked";reasons.append("admission_not_yet_effective")
  elif a>=min(limits):status="expired";reasons.append("authorization_lifetime_expired")
  elif x>min(limits):status="blocked";reasons.append("admission_exceeds_authorization_lifetime");errors.append("expiry_out_of_bounds")
  else:status="admitted";reasons.append("runtime_activation_admitted")
 base={k:v for k,v in u.items() if k not in {"schema","preparation_id","fingerprint","status",*RUNTIME_ACTIVATION_ADMISSION_STATUSES,"runtime_activation_preparation_created","reasons","errors"}}
 base.update({"schema":CAPABILITY_RUNTIME_ACTIVATION_ADMISSION_SCHEMA,"status":status,**{n:n==status for n in RUNTIME_ACTIVATION_ADMISSION_STATUSES},"admitted_at":at or "1970-01-01T00:00:00Z","admission_expires_at":xt or "1970-01-01T00:00:01Z","admission_ttl_seconds":ttl or DEFAULT_ADMISSION_TTL_SECONDS,"runtime_activation_preparation_id":_text(u.get("preparation_id")),"runtime_activation_preparation_fingerprint":_text(u.get("fingerprint")),"runtime_activation_preparation_status":_text(u.get("status")),"runtime_admission_created":status=="admitted","runtime_activation_admitted":status=="admitted",**{n:False for n in _FALSE_FLAGS if n not in {"runtime_activation_preparation_created","runtime_admission_created"}},"reasons":sorted(set(reasons)),"errors":sorted(set(errors))})
 r=_identity(base,"admission","capability-runtime-activation-admission-")
 from core.runtime.runtime_capability_runtime_activation_admission_validation import validate_capability_runtime_activation_admission
 if not validate_capability_runtime_activation_admission(r).valid:raise RuntimeError("internal admission validation failed")
 return r
__all__=["CAPABILITY_RUNTIME_ACTIVATION_ADMISSION_SCHEMA","RUNTIME_ACTIVATION_ADMISSION_STATUSES","DEFAULT_ADMISSION_TTL_SECONDS","MAXIMUM_ADMISSION_TTL_SECONDS","admit_capability_runtime_activation"]
