from __future__ import annotations
from datetime import datetime,timedelta,timezone
import hashlib,json
from typing import Any,Mapping
from core.runtime.runtime_capability_bootstrap_plan import canonical_json
CAPABILITY_AUTHORIZATION_TOKEN_ISSUANCE_SCHEMA="zero.runtime.capability_authorization_token_issuance.v1"
TOKEN_ISSUANCE_STATUSES=frozenset({"issued","not_issued","blocked","invalid","expired"})
DEFAULT_ISSUANCE_TTL_SECONDS=60;MAX_ISSUANCE_TTL_SECONDS=120
_LINEAGES=("active_authorization_preparation","active_authorization_eligibility","authorization_review_decision","authorization_review_request","review_policy","review_handoff","review","review_eligibility","activation_proposal","capability_profile","capability_strategy")
_FLAGS=("token_signed","token_handed_off","token_material_created","bearer_credential_created","runtime_activated","execution_authority_granted")
_FORBIDDEN=frozenset({"token_value","token_secret","bearer_token","credential","api_key","session_key","private_key","public_key","signature","signed_payload","mac","nonce","random_bytes","secret","password","delivery_payload","executor_ticket","may_execute","executor_allowed","runtime_started"})
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
def issue_capability_authorization_token(token_issuance_preparation:Any,*,issued_at:Any=None,issuance_expires_at:Any=None,issuance_ttl_seconds:Any=None)->dict[str,Any]:
 u=dict(token_issuance_preparation) if isinstance(token_issuance_preparation,Mapping) else {};it,i=_time(issued_at,True);xt,x=_time(issuance_expires_at)
 from core.runtime.runtime_capability_authorization_token_issuance_preparation_validation import validate_capability_authorization_token_issuance_preparation
 valid=validate_capability_authorization_token_issuance_preparation(u); reasons=[];errors=[];status="invalid"
 if issuance_ttl_seconds is None and x is not None and i is not None:
  d=(x-i).total_seconds();ttl=int(d) if d.is_integer() else d
 else:ttl=DEFAULT_ISSUANCE_TTL_SECONDS if issuance_ttl_seconds is None else issuance_ttl_seconds
 good=isinstance(ttl,int) and not isinstance(ttl,bool) and 0<ttl<=MAX_ISSUANCE_TTL_SECONDS
 if i is None:errors.append("invalid_issued_at")
 if issuance_expires_at is not None and x is None:errors.append("invalid_issuance_expires_at")
 if not good:errors.append("invalid_issuance_ttl")
 if i is not None and good:
  calc=i+timedelta(seconds=ttl)
  if x is None:x=calc
  elif x!=calc:errors.append("ttl_mismatch");x=calc
 forged=any(n in u and u.get(n) is not False for n in ("issuance_record_created","token_issued")+_FLAGS) or bool(set(u)&_FORBIDDEN)
 if forged:status="blocked";reasons.append("authority_flag_violation");errors.append("issuance_state_violation")
 elif not valid.valid:reasons.append("issuance_preparation_invalid");errors.append("invalid_issuance_preparation")
 elif errors:status="blocked";reasons.append("policy_precondition_blocked")
 else:
  _,te=_time(u.get("token_expires_at"));_,ae=_time(u.get("authorization_expires_at"));s=u["status"]
  if s=="not_prepared":status="not_issued";reasons.append("issuance_not_prepared_not_issued")
  elif s=="blocked":status="blocked";reasons.append("issuance_preparation_blocked")
  elif s=="invalid":status="invalid";reasons.append("issuance_preparation_invalid")
  elif s=="expired":status="expired";reasons.append("token_expired")
  elif i<_time(u.get("token_created_at"))[1]:status="blocked";reasons.append("token_not_yet_effective")
  elif i>=te or i>=ae:status="expired";reasons.append("token_expired_before_issuance")
  elif x>te or x>ae:
   if issuance_expires_at is None and issuance_ttl_seconds is None:
    x=min(te,ae);ttl=int((x-i).total_seconds());reasons.append("issuance_ttl_bounded_to_upstream");status="issued" if ttl>0 else "expired"
    reasons.append("issuance_record_created" if ttl>0 else "token_expired_before_issuance")
   else:
    status="blocked";reasons.append("policy_precondition_blocked");errors.append("issuance_expiry_exceeds_upstream");x=min(te,ae);ttl=max(1,int((x-i).total_seconds()))
  else:status="issued";reasons.append("issuance_record_created")
 epoch=datetime(1970,1,1,tzinfo=timezone.utc);si=i or epoch;sx=x or si+timedelta(seconds=DEFAULT_ISSUANCE_TTL_SECONDS)
 if sx<=si:sx=si+timedelta(seconds=1)
 sttl=int((sx-si).total_seconds())
 base={"schema":CAPABILITY_AUTHORIZATION_TOKEN_ISSUANCE_SCHEMA,"status":status,**{n:n==status for n in TOKEN_ISSUANCE_STATUSES},"issued_at":si.isoformat().replace("+00:00","Z"),"issuance_expires_at":sx.isoformat().replace("+00:00","Z"),"issuance_ttl_seconds":sttl,
 "token_issuance_preparation_id":_text(u.get("preparation_id")),"token_issuance_preparation_fingerprint":_text(u.get("fingerprint")),"token_issuance_preparation_status":_text(u.get("status")),"issuance_prepared_at":_time(u.get("prepared_at"))[0] or "1970-01-01T00:00:00Z",
 "token_issuance_eligibility_id":_text(u.get("token_issuance_eligibility_id")),"token_issuance_eligibility_fingerprint":_text(u.get("token_issuance_eligibility_fingerprint")),"authorization_token_id":_text(u.get("authorization_token_id")),"authorization_token_fingerprint":_text(u.get("authorization_token_fingerprint")),"authorization_token_preparation_id":_text(u.get("authorization_token_preparation_id")),"authorization_token_preparation_fingerprint":_text(u.get("authorization_token_preparation_fingerprint")),"authorization_token_eligibility_id":_text(u.get("authorization_token_eligibility_id")),"authorization_token_eligibility_fingerprint":_text(u.get("authorization_token_eligibility_fingerprint")),"active_authorization_id":_text(u.get("active_authorization_id")),"active_authorization_fingerprint":_text(u.get("active_authorization_fingerprint")),
 "token_created_at":_time(u.get("token_created_at"))[0] or "1970-01-01T00:00:00Z","token_expires_at":_time(u.get("token_expires_at"))[0] or "1970-01-01T00:00:01Z","token_ttl_seconds":u.get("token_ttl_seconds") if isinstance(u.get("token_ttl_seconds"),int) and not isinstance(u.get("token_ttl_seconds"),bool) and u.get("token_ttl_seconds")>0 else 1,"authorized_at":_time(u.get("authorized_at"))[0] or "1970-01-01T00:00:00Z","authorization_expires_at":_time(u.get("authorization_expires_at"))[0] or "1970-01-01T00:00:01Z","authorization_ttl_seconds":u.get("authorization_ttl_seconds") if isinstance(u.get("authorization_ttl_seconds"),int) and not isinstance(u.get("authorization_ttl_seconds"),bool) and u.get("authorization_ttl_seconds")>0 else 1,
 "issuance_record_created":status=="issued","token_issued":status=="issued",**{n:False for n in _FLAGS},"reasons":sorted(set(reasons)),"errors":sorted(set(errors))}
 for z in _LINEAGES:base[z+"_id"]=_text(u.get(z+"_id"));base[z+"_fingerprint"]=_text(u.get(z+"_fingerprint"))
 f=_hash(base);base["issuance_id"]="capability-authorization-token-issuance-"+f[:24];base["fingerprint"]=f;r=json.loads(canonical_json(base))
 from core.runtime.runtime_capability_authorization_token_issuance_validation import validate_capability_authorization_token_issuance
 if not validate_capability_authorization_token_issuance(r).valid:raise RuntimeError("internal issuance validation failed")
 return r
__all__=["CAPABILITY_AUTHORIZATION_TOKEN_ISSUANCE_SCHEMA","TOKEN_ISSUANCE_STATUSES","DEFAULT_ISSUANCE_TTL_SECONDS","MAX_ISSUANCE_TTL_SECONDS","issue_capability_authorization_token"]
