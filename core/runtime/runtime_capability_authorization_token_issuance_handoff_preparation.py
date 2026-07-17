from __future__ import annotations
from datetime import datetime,timezone
import hashlib,json
from typing import Any,Mapping
from core.runtime.runtime_capability_bootstrap_plan import canonical_json
CAPABILITY_AUTHORIZATION_TOKEN_ISSUANCE_HANDOFF_PREPARATION_SCHEMA="zero.runtime.capability_authorization_token_issuance_handoff_preparation.v1"
HANDOFF_PREPARATION_STATUSES=frozenset({"prepared","not_prepared","blocked","invalid","expired"})
_LINEAGES=("active_authorization_preparation","active_authorization_eligibility","authorization_review_decision","authorization_review_request","review_policy","review_handoff","review","review_eligibility","activation_proposal","capability_profile","capability_strategy")
_FLAGS=("token_handed_off","handoff_completed","token_signed","token_material_created","bearer_credential_created","runtime_activated","execution_authority_granted")
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
def prepare_capability_authorization_token_issuance_handoff(token_issuance:Any,*,prepared_at:Any=None)->dict[str,Any]:
 u=dict(token_issuance) if isinstance(token_issuance,Mapping) else {};pt,p=_time(prepared_at,True)
 from core.runtime.runtime_capability_authorization_token_issuance_validation import validate_capability_authorization_token_issuance
 valid=validate_capability_authorization_token_issuance(u);reasons=[];errors=[];status="invalid"
 forged=any(n in u and u.get(n) is not False for n in ("token_handed_off","token_signed","token_material_created","bearer_credential_created","runtime_activated","execution_authority_granted")) or bool(set(u)&_FORBIDDEN)
 if p is None:reasons.append("token_issuance_invalid");errors.append("invalid_prepared_at")
 elif forged:status="blocked";reasons.append("authority_flag_violation");errors.append("handoff_state_violation")
 elif not valid.valid:reasons.append("token_issuance_invalid");errors.append("invalid_token_issuance")
 else:
  _,issued=_time(u.get("issued_at"));_,ie=_time(u.get("issuance_expires_at"));_,te=_time(u.get("token_expires_at"));_,ae=_time(u.get("authorization_expires_at"));s=u["status"]
  if s=="not_issued":status="not_prepared";reasons.append("token_not_issued_handoff_not_prepared")
  elif s=="blocked":status="blocked";reasons.append("token_issuance_blocked")
  elif s=="invalid":status="invalid";reasons.append("token_issuance_invalid")
  elif s=="expired":status="expired";reasons.append("token_issuance_expired")
  elif p<issued:status="blocked";reasons.append("issuance_not_yet_effective")
  elif p>=min(ie,te,ae):status="expired";reasons.append("issuance_expired_before_handoff_preparation")
  else:status="prepared";reasons.append("issuance_handoff_preparation_ready")
 epoch="1970-01-01T00:00:00Z";one="1970-01-01T00:00:01Z"
 base={"schema":CAPABILITY_AUTHORIZATION_TOKEN_ISSUANCE_HANDOFF_PREPARATION_SCHEMA,"status":status,**{n:n==status for n in HANDOFF_PREPARATION_STATUSES},"prepared_at":pt or epoch,
 "token_issuance_id":_text(u.get("issuance_id")),"token_issuance_fingerprint":_text(u.get("fingerprint")),"token_issuance_status":_text(u.get("status")),"issued_at":_time(u.get("issued_at"))[0] or epoch,"issuance_expires_at":_time(u.get("issuance_expires_at"))[0] or one,"issuance_ttl_seconds":u.get("issuance_ttl_seconds") if isinstance(u.get("issuance_ttl_seconds"),int) and not isinstance(u.get("issuance_ttl_seconds"),bool) and u.get("issuance_ttl_seconds")>0 else 1,
 "token_issuance_preparation_id":_text(u.get("token_issuance_preparation_id")),"token_issuance_preparation_fingerprint":_text(u.get("token_issuance_preparation_fingerprint")),"token_issuance_eligibility_id":_text(u.get("token_issuance_eligibility_id")),"token_issuance_eligibility_fingerprint":_text(u.get("token_issuance_eligibility_fingerprint")),"authorization_token_id":_text(u.get("authorization_token_id")),"authorization_token_fingerprint":_text(u.get("authorization_token_fingerprint")),"authorization_token_preparation_id":_text(u.get("authorization_token_preparation_id")),"authorization_token_preparation_fingerprint":_text(u.get("authorization_token_preparation_fingerprint")),"authorization_token_eligibility_id":_text(u.get("authorization_token_eligibility_id")),"authorization_token_eligibility_fingerprint":_text(u.get("authorization_token_eligibility_fingerprint")),"active_authorization_id":_text(u.get("active_authorization_id")),"active_authorization_fingerprint":_text(u.get("active_authorization_fingerprint")),
 "token_created_at":_time(u.get("token_created_at"))[0] or epoch,"token_expires_at":_time(u.get("token_expires_at"))[0] or one,"authorized_at":_time(u.get("authorized_at"))[0] or epoch,"authorization_expires_at":_time(u.get("authorization_expires_at"))[0] or one,
 "handoff_preparation_created":status=="prepared",**{n:False for n in _FLAGS},"reasons":sorted(set(reasons)),"errors":sorted(set(errors))}
 for z in _LINEAGES:base[z+"_id"]=_text(u.get(z+"_id"));base[z+"_fingerprint"]=_text(u.get(z+"_fingerprint"))
 f=_hash(base);base["handoff_preparation_id"]="capability-authorization-token-issuance-handoff-preparation-"+f[:24];base["fingerprint"]=f;r=json.loads(canonical_json(base))
 from core.runtime.runtime_capability_authorization_token_issuance_handoff_preparation_validation import validate_capability_authorization_token_issuance_handoff_preparation
 if not validate_capability_authorization_token_issuance_handoff_preparation(r).valid:raise RuntimeError("internal handoff preparation validation failed")
 return r
__all__=["CAPABILITY_AUTHORIZATION_TOKEN_ISSUANCE_HANDOFF_PREPARATION_SCHEMA","HANDOFF_PREPARATION_STATUSES","prepare_capability_authorization_token_issuance_handoff"]
