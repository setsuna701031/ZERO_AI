from __future__ import annotations
import re
from typing import Any,Mapping
from core.runtime.runtime_capability_runtime_activation_eligibility import _time,_text,_identity

CAPABILITY_ACTIVATION_CONSUMER_ACCEPTANCE_SCHEMA="zero.runtime.capability_activation_consumer_acceptance.v1"
ACTIVATION_CONSUMER_ACCEPTANCE_STATUSES=frozenset({"accepted","not_accepted","blocked","invalid","expired"})
MAX_GOVERNANCE_ID_LENGTH=128
_EXPIRIES=("admission_expires_at","issuance_expires_at","token_expires_at","authorization_expires_at")
_LINEAGES=("capability_profile","capability_strategy","activation_proposal","review_eligibility","review","review_handoff","review_policy","authorization_review_request","authorization_review_decision","active_authorization_eligibility","active_authorization_preparation","active_authorization","authorization_token_eligibility","authorization_token_preparation","authorization_token","token_issuance_eligibility","token_issuance_preparation","token_issuance","token_issuance_handoff_preparation","token_issuance_handoff","runtime_activation_eligibility","runtime_activation_preparation","runtime_activation_admission","runtime_activation_admission_handoff")
_FORBIDDEN=frozenset({"command","command_line","argv","environment","env","working_directory","executable","binary","process_id","pid","stdout","stderr","model_path","model_name","device_id","gpu_id","tool_name","tool_arguments","executor_ticket","execution_plan","mutation_plan","session_secret","credential","token_value","bearer_token","signature","private_key","endpoint","url","host","port","socket","transport","network_address","filesystem_path","pipe","queue","topic"})
_SAFETY_FLAGS=("activation_command_created","activation_attempted","runtime_process_started","runtime_activated","executor_admitted","execution_session_created","execution_authority_granted")
def _governance_id(v:Any):
 if not isinstance(v,str):return None
 x=v.strip()
 if not x or len(x)>MAX_GOVERNANCE_ID_LENGTH or any(ord(c)<32 or ord(c)==127 for c in x) or re.search(r"://|[\\/]|^\w+:\d+$",x) or x.lower().startswith(("socket:","pipe:","queue:","topic:")):return None
 return x
def _link(base:dict[str,Any],u:Mapping[str,Any],current:str,current_id:str)->None:
 for z in _LINEAGES:
  if z==current:base[z+"_id"]=_text(u.get(current_id));base[z+"_fingerprint"]=_text(u.get("fingerprint"))
  else:base[z+"_id"]=_text(u.get(z+"_id"));base[z+"_fingerprint"]=_text(u.get(z+"_fingerprint"))
def _bad_flags(u:Mapping[str,Any],allowed:frozenset[str]=frozenset())->bool:return bool(set(u)&_FORBIDDEN) or any(n in u and n not in allowed and u.get(n) is not False for n in _SAFETY_FLAGS)

def accept_capability_activation_consumer_handoff(runtime_activation_admission_handoff:Any,*,accepted_at:Any=None,consumer_id:Any=None)->dict[str,Any]:
 u=dict(runtime_activation_admission_handoff) if isinstance(runtime_activation_admission_handoff,Mapping) else {};at,a=_time(accepted_at,True);consumer=_governance_id(consumer_id);reasons=[];errors=[];status="invalid"
 from core.runtime.runtime_capability_runtime_activation_admission_handoff_validation import validate_capability_runtime_activation_admission_handoff
 valid=validate_capability_runtime_activation_admission_handoff(u)
 if a is None:errors.append("invalid_accepted_at")
 if consumer is None:errors.append("invalid_consumer_id")
 if _bad_flags(u):status="blocked";reasons.append("authority_flag_violation");errors.append("activation_state_violation")
 elif not valid.valid:reasons.append("runtime_activation_admission_handoff_invalid");errors.append("invalid_runtime_activation_admission_handoff")
 elif errors:status="blocked";reasons.append("consumer_governance_blocked")
 else:
  _,h=_time(u.get("handed_off_at"));limits=[_time(u.get(n))[1] for n in _EXPIRIES];s=u["status"]
  if s=="not_handed_off":status="not_accepted";reasons.append("activation_handoff_not_available")
  elif s in {"blocked","invalid","expired"}:status=s;reasons.append("activation_handoff_"+s)
  elif a<h:status="blocked";reasons.append("acceptance_not_yet_effective")
  elif a>=min(limits):status="expired";reasons.append("activation_admission_expired")
  else:status="accepted";reasons.append("activation_handoff_accepted")
 base={"schema":CAPABILITY_ACTIVATION_CONSUMER_ACCEPTANCE_SCHEMA,"status":status,**{n:n==status for n in ACTIVATION_CONSUMER_ACCEPTANCE_STATUSES},"accepted_at":at or "1970-01-01T00:00:00Z","consumer_id":consumer or "unavailable","handoff_timestamp":_time(u.get("handed_off_at"))[0] or "1970-01-01T00:00:00Z",**{n:_time(u.get(n))[0] or "1970-01-01T00:00:01Z" for n in _EXPIRIES},"activation_consumer_acceptance_created":status=="accepted","activation_handoff_accepted":status=="accepted",**{n:False for n in _SAFETY_FLAGS},"reasons":sorted(set(reasons)),"errors":sorted(set(errors))};_link(base,u,"runtime_activation_admission_handoff","handoff_id")
 r=_identity(base,"acceptance","capability-activation-consumer-acceptance-")
 from core.runtime.runtime_capability_activation_consumer_acceptance_validation import validate_capability_activation_consumer_acceptance
 if not validate_capability_activation_consumer_acceptance(r).valid:raise RuntimeError("internal consumer acceptance validation failed")
 return r
__all__=["CAPABILITY_ACTIVATION_CONSUMER_ACCEPTANCE_SCHEMA","ACTIVATION_CONSUMER_ACCEPTANCE_STATUSES","MAX_GOVERNANCE_ID_LENGTH","accept_capability_activation_consumer_handoff"]
