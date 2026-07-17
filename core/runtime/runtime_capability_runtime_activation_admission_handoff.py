from __future__ import annotations
import re
from typing import Any,Mapping
from core.runtime.runtime_capability_runtime_activation_eligibility import _FALSE_FLAGS,_FORBIDDEN,_time,_text,_identity
CAPABILITY_RUNTIME_ACTIVATION_ADMISSION_HANDOFF_SCHEMA="zero.runtime.capability_runtime_activation_admission_handoff.v1"
RUNTIME_ACTIVATION_ADMISSION_HANDOFF_STATUSES=frozenset({"handed_off","not_handed_off","blocked","invalid","expired"})
MAX_RECIPIENT_ID_LENGTH=128
def _recipient(v:Any):
 if not isinstance(v,str):return None
 x=v.strip()
 if not x or len(x)>MAX_RECIPIENT_ID_LENGTH or any(ord(c)<32 or ord(c)==127 for c in x) or re.search(r"://|[\\/]|^\w+:\d+$",x):return None
 return x
def create_capability_runtime_activation_admission_handoff(runtime_activation_admission:Any,*,handed_off_at:Any=None,recipient_id:Any=None)->dict[str,Any]:
 u=dict(runtime_activation_admission) if isinstance(runtime_activation_admission,Mapping) else {};ht,h=_time(handed_off_at,True);recipient=_recipient("runtime-activation-consumer" if recipient_id is None else recipient_id);reasons=[];errors=[];status="invalid"
 from core.runtime.runtime_capability_runtime_activation_admission_validation import validate_capability_runtime_activation_admission
 valid=validate_capability_runtime_activation_admission(u);forged=bool(set(u)&_FORBIDDEN) or any(u.get(n) is not False for n in _FALSE_FLAGS if n in u and n not in {"runtime_activation_preparation_created","runtime_admission_created"})
 if h is None:errors.append("invalid_handed_off_at")
 if recipient is None:errors.append("invalid_recipient_id")
 if forged:status="blocked";reasons.append("authority_flag_violation");errors.append("runtime_state_violation")
 elif not valid.valid:reasons.append("runtime_activation_admission_invalid");errors.append("invalid_runtime_activation_admission")
 elif errors:status="blocked";reasons.append("handoff_policy_blocked")
 else:
  _,a=_time(u.get("admitted_at"));limits=[_time(u.get(n))[1] for n in ("admission_expires_at","issuance_expires_at","token_expires_at","authorization_expires_at")];s=u["status"]
  if s=="not_admitted":status="not_handed_off";reasons.append("runtime_activation_not_admitted")
  elif s in {"blocked","invalid","expired"}:status=s;reasons.append("runtime_activation_admission_"+s)
  elif h<a:status="blocked";reasons.append("handoff_not_yet_effective")
  elif h>=min(limits):status="expired";reasons.append("runtime_activation_admission_expired")
  else:status="handed_off";reasons.append("runtime_activation_admission_handed_off")
 base={k:v for k,v in u.items() if k not in {"schema","admission_id","fingerprint","status",*RUNTIME_ACTIVATION_ADMISSION_HANDOFF_STATUSES,"runtime_admission_created","runtime_activation_admitted","reasons","errors"}}
 base.update({"schema":CAPABILITY_RUNTIME_ACTIVATION_ADMISSION_HANDOFF_SCHEMA,"status":status,**{n:n==status for n in RUNTIME_ACTIVATION_ADMISSION_HANDOFF_STATUSES},"handed_off_at":ht or "1970-01-01T00:00:00Z","recipient_id":recipient or "unavailable","runtime_activation_admission_id":_text(u.get("admission_id")),"runtime_activation_admission_fingerprint":_text(u.get("fingerprint")),"runtime_activation_admission_status":_text(u.get("status")),"runtime_admission_handoff_created":status=="handed_off","runtime_admission_handed_off":status=="handed_off","handoff_delivered":False,"handoff_acknowledged":False,**{n:False for n in _FALSE_FLAGS if n not in {"runtime_activation_preparation_created","runtime_admission_created"}},"reasons":sorted(set(reasons)),"errors":sorted(set(errors))})
 r=_identity(base,"handoff","capability-runtime-activation-admission-handoff-")
 from core.runtime.runtime_capability_runtime_activation_admission_handoff_validation import validate_capability_runtime_activation_admission_handoff
 if not validate_capability_runtime_activation_admission_handoff(r).valid:raise RuntimeError("internal admission handoff validation failed")
 return r
__all__=["CAPABILITY_RUNTIME_ACTIVATION_ADMISSION_HANDOFF_SCHEMA","RUNTIME_ACTIVATION_ADMISSION_HANDOFF_STATUSES","MAX_RECIPIENT_ID_LENGTH","create_capability_runtime_activation_admission_handoff"]
