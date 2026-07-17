from __future__ import annotations
from datetime import datetime, timezone
import hashlib, json
from typing import Any, Mapping
from core.runtime.runtime_capability_bootstrap_plan import canonical_json

CAPABILITY_RUNTIME_ACTIVATION_ELIGIBILITY_SCHEMA="zero.runtime.capability_runtime_activation_eligibility.v1"
RUNTIME_ACTIVATION_ELIGIBILITY_STATUSES=frozenset({"eligible","ineligible","blocked","invalid","expired"})
_UPSTREAM=("token_issuance_handoff","token_issuance_handoff_preparation","token_issuance","token_issuance_preparation","token_issuance_eligibility","authorization_token","authorization_token_preparation","authorization_token_eligibility","active_authorization","active_authorization_preparation","active_authorization_eligibility","authorization_review_decision","authorization_review_request","review_policy","review_handoff","review","review_eligibility","activation_proposal","capability_strategy","capability_profile")
_FALSE_FLAGS=("runtime_activation_preparation_created","runtime_admission_created","runtime_activation_command_created","runtime_process_started","runtime_activated","executor_admitted","execution_session_created","mutation_authority_granted","execution_authority_granted")
_FORBIDDEN=frozenset({"command","command_line","argv","environment","env","working_directory","executable","binary","process_id","pid","model_path","model_name","device_id","gpu_id","tool_name","tool_arguments","executor_ticket","execution_plan","mutation_plan","session_secret","credential","token_value","bearer_token","signature","endpoint","url","host","port","socket","transport","network_address","filesystem_path","pipe","queue","topic"})

def _hash(v:Any)->str:return hashlib.sha256(canonical_json(v).encode()).hexdigest()
def _time(v:Any,now:bool=False):
 if v is None:p=datetime.now(timezone.utc) if now else None
 elif isinstance(v,datetime):p=v
 elif isinstance(v,str):
  try:p=datetime.fromisoformat(v.replace("Z","+00:00"))
  except ValueError:p=None
 else:p=None
 if p is None or p.tzinfo is None or p.utcoffset() is None:return None,None
 p=p.astimezone(timezone.utc);return p.isoformat().replace("+00:00","Z"),p
def _text(v:Any)->str:return v if isinstance(v,str) and v else "unavailable"
def _identity(base:dict[str,Any],kind:str,prefix:str)->dict[str,Any]:
 f=_hash(base);base[kind+"_id"]=prefix+f[:24];base["fingerprint"]=f;return json.loads(canonical_json(base))

def evaluate_capability_runtime_activation_eligibility(token_issuance_handoff:Any,*,evaluated_at:Any=None)->dict[str,Any]:
 u=dict(token_issuance_handoff) if isinstance(token_issuance_handoff,Mapping) else {};et,e=_time(evaluated_at,True);reasons=[];errors=[];status="invalid"
 from core.runtime.runtime_capability_authorization_token_issuance_handoff_validation import validate_capability_authorization_token_issuance_handoff
 valid=validate_capability_authorization_token_issuance_handoff(u)
 forged=bool(set(u)&_FORBIDDEN) or any(u.get(n) is not False for n in _FALSE_FLAGS if n in u)
 if e is None:errors.append("invalid_evaluated_at")
 if forged:status="blocked";reasons.append("authority_flag_violation");errors.append("runtime_state_violation")
 elif not valid.valid:reasons.append("token_issuance_handoff_invalid");errors.append("invalid_token_issuance_handoff")
 else:
  _,h=_time(u.get("handed_off_at"));_,ie=_time(u.get("issuance_expires_at"));_,te=_time(u.get("token_expires_at"));_,ae=_time(u.get("authorization_expires_at"));s=u["status"]
  if s=="not_handed_off":status="ineligible";reasons.append("token_not_handed_off")
  elif s=="blocked":status="blocked";reasons.append("token_handoff_blocked")
  elif s=="invalid":status="invalid";reasons.append("token_handoff_invalid")
  elif s=="expired":status="expired";reasons.append("token_handoff_expired")
  elif e<h:status="blocked";reasons.append("eligibility_not_yet_effective")
  elif e>=min(ie,te,ae):status="expired";reasons.append("authorization_lifetime_expired")
  else:status="eligible";reasons.append("runtime_activation_eligible")
 epoch="1970-01-01T00:00:00Z";one="1970-01-01T00:00:01Z"
 base={"schema":CAPABILITY_RUNTIME_ACTIVATION_ELIGIBILITY_SCHEMA,"status":status,**{n:n==status for n in RUNTIME_ACTIVATION_ELIGIBILITY_STATUSES},"evaluated_at":et or epoch,"token_handed_off_at":_time(u.get("handed_off_at"))[0] or epoch,"recipient_id":_text(u.get("recipient_id")),"issued_at":_time(u.get("issued_at"))[0] or epoch,"issuance_expires_at":_time(u.get("issuance_expires_at"))[0] or one,"token_created_at":_time(u.get("token_created_at"))[0] or epoch,"token_expires_at":_time(u.get("token_expires_at"))[0] or one,"authorized_at":_time(u.get("authorized_at"))[0] or epoch,"authorization_expires_at":_time(u.get("authorization_expires_at"))[0] or one,"runtime_activation_eligibility_confirmed":status=="eligible",**{n:False for n in _FALSE_FLAGS},"reasons":sorted(set(reasons)),"errors":sorted(set(errors))}
 for z in _UPSTREAM:base[z+"_id"]=_text(u.get("handoff_id") if z=="token_issuance_handoff" else u.get(z+"_id"));base[z+"_fingerprint"]=_text(u.get("fingerprint") if z=="token_issuance_handoff" else u.get(z+"_fingerprint"))
 r=_identity(base,"eligibility","capability-runtime-activation-eligibility-")
 from core.runtime.runtime_capability_runtime_activation_eligibility_validation import validate_capability_runtime_activation_eligibility
 if not validate_capability_runtime_activation_eligibility(r).valid:raise RuntimeError("internal eligibility validation failed")
 return r
__all__=["CAPABILITY_RUNTIME_ACTIVATION_ELIGIBILITY_SCHEMA","RUNTIME_ACTIVATION_ELIGIBILITY_STATUSES","evaluate_capability_runtime_activation_eligibility"]
