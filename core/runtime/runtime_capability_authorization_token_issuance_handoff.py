from __future__ import annotations
from datetime import datetime,timezone
import hashlib,json,re
from typing import Any,Mapping
from core.runtime.runtime_capability_bootstrap_plan import canonical_json
CAPABILITY_AUTHORIZATION_TOKEN_ISSUANCE_HANDOFF_SCHEMA="zero.runtime.capability_authorization_token_issuance_handoff.v1"
TOKEN_ISSUANCE_HANDOFF_STATUSES=frozenset({"handed_off","not_handed_off","blocked","invalid","expired"})
MAX_RECIPIENT_ID_LENGTH=128
_LINEAGES=("active_authorization_preparation","active_authorization_eligibility","authorization_review_decision","authorization_review_request","review_policy","review_handoff","review","review_eligibility","activation_proposal","capability_profile","capability_strategy")
_FLAGS=("handoff_delivered","handoff_acknowledged","token_signed","token_material_created","bearer_credential_created","runtime_activated","execution_authority_granted","executor_admitted")
_FORBIDDEN=frozenset({"token_value","token_secret","bearer_token","credential","api_key","session_key","private_key","public_key","signature","signed_payload","mac","nonce","random_bytes","secret","password","delivery_payload","executor_ticket","endpoint","url","host","port","socket","transport","network_address","filesystem_path","may_execute","executor_allowed"})
def _hash(v):return hashlib.sha256(canonical_json(v).encode()).hexdigest()
def _time(v,now=False):
 if v is None:p=datetime.now(timezone.utc) if now else None
 elif isinstance(v,datetime):p=v
 elif isinstance(v,str):
  try:p=datetime.fromisoformat(v.replace("Z","+00:00"))
  except ValueError:p=None
 else:p=None
 if p is None or p.tzinfo is None or p.utcoffset() is None:return None,None
 p=p.astimezone(timezone.utc);return p.isoformat().replace("+00:00","Z"),p
def _text(v):return v if isinstance(v,str) and v else "unavailable"
def _recipient(v):
 if not isinstance(v,str):return None
 x=v.strip()
 if not x or len(x)>MAX_RECIPIENT_ID_LENGTH or any(ord(c)<32 or ord(c)==127 for c in x):return None
 if re.search(r"://|[\\/]|^\w+:\d+$",x):return None
 return x
def create_capability_authorization_token_issuance_handoff(token_issuance_handoff_preparation:Any,*,handed_off_at:Any=None,recipient_id:Any=None)->dict[str,Any]:
 u=dict(token_issuance_handoff_preparation) if isinstance(token_issuance_handoff_preparation,Mapping) else {};ht,h=_time(handed_off_at,True);recipient=_recipient(recipient_id)
 from core.runtime.runtime_capability_authorization_token_issuance_handoff_preparation_validation import validate_capability_authorization_token_issuance_handoff_preparation
 valid=validate_capability_authorization_token_issuance_handoff_preparation(u);reasons=[];errors=[];status="invalid"
 forged=any(n in u and u.get(n) is not False for n in ("token_handed_off","handoff_completed","token_signed","token_material_created","bearer_credential_created","runtime_activated","execution_authority_granted")) or bool(set(u)&_FORBIDDEN)
 if h is None:errors.append("invalid_handed_off_at")
 if recipient is None:errors.append("invalid_recipient_id")
 if forged:status="blocked";reasons.append("authority_flag_violation");errors.append("handoff_state_violation")
 elif not valid.valid:reasons.append("handoff_preparation_invalid");errors.append("invalid_handoff_preparation")
 elif errors:status="blocked";reasons.append("policy_precondition_blocked")
 else:
  _,hp=_time(u.get("prepared_at"));_,ie=_time(u.get("issuance_expires_at"));_,te=_time(u.get("token_expires_at"));_,ae=_time(u.get("authorization_expires_at"));s=u["status"]
  if s=="not_prepared":status="not_handed_off";reasons.append("handoff_not_prepared_not_handed_off")
  elif s=="blocked":status="blocked";reasons.append("handoff_preparation_blocked")
  elif s=="invalid":status="invalid";reasons.append("handoff_preparation_invalid")
  elif s=="expired":status="expired";reasons.append("issuance_expired")
  elif h<hp:status="blocked";reasons.append("handoff_not_yet_effective")
  elif h>=min(ie,te,ae):status="expired";reasons.append("issuance_expired_before_handoff")
  else:status="handed_off";reasons.append("issuance_handoff_record_created")
 epoch="1970-01-01T00:00:00Z";one="1970-01-01T00:00:01Z"
 base={"schema":CAPABILITY_AUTHORIZATION_TOKEN_ISSUANCE_HANDOFF_SCHEMA,"status":status,**{n:n==status for n in TOKEN_ISSUANCE_HANDOFF_STATUSES},"handed_off_at":ht or epoch,"recipient_id":recipient or "unavailable",
 "token_issuance_handoff_preparation_id":_text(u.get("handoff_preparation_id")),"token_issuance_handoff_preparation_fingerprint":_text(u.get("fingerprint")),"token_issuance_handoff_preparation_status":_text(u.get("status")),"handoff_prepared_at":_time(u.get("prepared_at"))[0] or epoch,
 "token_issuance_id":_text(u.get("token_issuance_id")),"token_issuance_fingerprint":_text(u.get("token_issuance_fingerprint")),"token_issuance_preparation_id":_text(u.get("token_issuance_preparation_id")),"token_issuance_preparation_fingerprint":_text(u.get("token_issuance_preparation_fingerprint")),"token_issuance_eligibility_id":_text(u.get("token_issuance_eligibility_id")),"token_issuance_eligibility_fingerprint":_text(u.get("token_issuance_eligibility_fingerprint")),"authorization_token_id":_text(u.get("authorization_token_id")),"authorization_token_fingerprint":_text(u.get("authorization_token_fingerprint")),"authorization_token_preparation_id":_text(u.get("authorization_token_preparation_id")),"authorization_token_preparation_fingerprint":_text(u.get("authorization_token_preparation_fingerprint")),"authorization_token_eligibility_id":_text(u.get("authorization_token_eligibility_id")),"authorization_token_eligibility_fingerprint":_text(u.get("authorization_token_eligibility_fingerprint")),"active_authorization_id":_text(u.get("active_authorization_id")),"active_authorization_fingerprint":_text(u.get("active_authorization_fingerprint")),
 "issued_at":_time(u.get("issued_at"))[0] or epoch,"issuance_expires_at":_time(u.get("issuance_expires_at"))[0] or one,"token_created_at":_time(u.get("token_created_at"))[0] or epoch,"token_expires_at":_time(u.get("token_expires_at"))[0] or one,"authorized_at":_time(u.get("authorized_at"))[0] or epoch,"authorization_expires_at":_time(u.get("authorization_expires_at"))[0] or one,
 "handoff_record_created":status=="handed_off","token_handed_off":status=="handed_off",**{n:False for n in _FLAGS},"reasons":sorted(set(reasons)),"errors":sorted(set(errors))}
 for z in _LINEAGES:base[z+"_id"]=_text(u.get(z+"_id"));base[z+"_fingerprint"]=_text(u.get(z+"_fingerprint"))
 f=_hash(base);base["handoff_id"]="capability-authorization-token-issuance-handoff-"+f[:24];base["fingerprint"]=f;r=json.loads(canonical_json(base))
 from core.runtime.runtime_capability_authorization_token_issuance_handoff_validation import validate_capability_authorization_token_issuance_handoff
 if not validate_capability_authorization_token_issuance_handoff(r).valid:raise RuntimeError("internal handoff validation failed")
 return r
__all__=["CAPABILITY_AUTHORIZATION_TOKEN_ISSUANCE_HANDOFF_SCHEMA","TOKEN_ISSUANCE_HANDOFF_STATUSES","MAX_RECIPIENT_ID_LENGTH","create_capability_authorization_token_issuance_handoff"]
