from __future__ import annotations

from datetime import datetime, timezone
import hashlib, json
from typing import Any, Mapping

from core.runtime.runtime_capability_bootstrap_plan import canonical_json

CAPABILITY_AUTHORIZATION_TOKEN_ISSUANCE_PREPARATION_SCHEMA = "zero.runtime.capability_authorization_token_issuance_preparation.v1"
TOKEN_ISSUANCE_PREPARATION_STATUSES = frozenset({"prepared", "not_prepared", "blocked", "invalid", "expired"})
_LINEAGES = ("active_authorization_preparation", "active_authorization_eligibility", "authorization_review_decision", "authorization_review_request", "review_policy", "review_handoff", "review", "review_eligibility", "activation_proposal", "capability_profile", "capability_strategy")
_FLAGS = ("token_issued", "token_signed", "token_handed_off", "token_material_created", "runtime_activated", "execution_authority_granted")
_FORBIDDEN = frozenset({"token_value","token_secret","bearer_token","credential","api_key","session_key","private_key","public_key","signature","signed_payload","mac","nonce","random_bytes","secret","password","delivery_payload","executor_ticket","may_execute","executor_allowed","runtime_started"})

def _hash(v): return hashlib.sha256(canonical_json(v).encode("utf-8")).hexdigest()
def _time(v, now=False):
    if v is None: p = datetime.now(timezone.utc) if now else None
    elif isinstance(v, datetime): p = v
    elif isinstance(v, str):
        try: p = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError: p = None
    else: p = None
    if p is None or p.tzinfo is None or p.utcoffset() is None: return None, None
    p=p.astimezone(timezone.utc); return p.isoformat().replace("+00:00","Z"),p
def _text(v): return v if isinstance(v,str) and v else "unavailable"

def prepare_capability_authorization_token_issuance(token_issuance_eligibility: Any, *, prepared_at: Any=None) -> dict[str,Any]:
    upstream=dict(token_issuance_eligibility) if isinstance(token_issuance_eligibility,Mapping) else {}
    pt,p=_time(prepared_at,True)
    from core.runtime.runtime_capability_authorization_token_issuance_eligibility_validation import validate_capability_authorization_token_issuance_eligibility
    valid=validate_capability_authorization_token_issuance_eligibility(upstream)
    reasons=[]; errors=[]; status="invalid"
    forged=any(n in upstream and upstream.get(n) is not False for n in ("issuance_preparation_created",)+_FLAGS) or bool(set(upstream)&_FORBIDDEN)
    if p is None: reasons.append("issuance_eligibility_invalid"); errors.append("invalid_prepared_at")
    elif forged: status="blocked"; reasons.append("authority_flag_violation"); errors.append("issuance_state_violation")
    elif not valid.valid:
        reasons.append("issuance_eligibility_invalid"); errors.append("invalid_issuance_eligibility")
        trans={"invalid_schema":"invalid_schema","eligibility_id_mismatch":"invalid_identity","fingerprint_mismatch":"fingerprint_mismatch","invalid_status":"invalid_status","missing_linkage":"missing_linkage","inconsistent_status_flags":"inconsistent_flags"}
        errors += [trans[e] for e in valid.errors if e in trans]
    else:
        _,created=_time(upstream.get("token_created_at")); _,expiry=_time(upstream.get("token_expires_at")); _,auth_expiry=_time(upstream.get("authorization_expires_at"))
        s=upstream["status"]
        if s=="ineligible": status="not_prepared"; reasons.append("token_issuance_ineligible_not_prepared")
        elif s=="blocked": status="blocked"; reasons.append("token_issuance_eligibility_blocked")
        elif s=="invalid": status="invalid"; reasons.append("issuance_eligibility_invalid")
        elif s=="expired": status="expired"; reasons.append("token_expired")
        elif p < created: status="blocked"; reasons.append("token_not_yet_effective")
        elif p >= expiry or p >= auth_expiry: status="expired"; reasons.append("token_expired_before_issuance_preparation")
        else: status="prepared"; reasons.append("token_issuance_preparation_ready")
    epoch="1970-01-01T00:00:00Z"; one="1970-01-01T00:00:01Z"
    base={"schema":CAPABILITY_AUTHORIZATION_TOKEN_ISSUANCE_PREPARATION_SCHEMA,"status":status,**{n:n==status for n in TOKEN_ISSUANCE_PREPARATION_STATUSES},"prepared_at":pt or epoch,
      "token_issuance_eligibility_id":_text(upstream.get("eligibility_id")),"token_issuance_eligibility_fingerprint":_text(upstream.get("fingerprint")),"token_issuance_eligibility_status":_text(upstream.get("status")),"issuance_eligibility_evaluated_at":_time(upstream.get("evaluated_at"))[0] or epoch,
      "authorization_token_id":_text(upstream.get("authorization_token_id")),"authorization_token_fingerprint":_text(upstream.get("authorization_token_fingerprint")),"authorization_token_status":_text(upstream.get("authorization_token_status")),
      "token_created_at":_time(upstream.get("token_created_at"))[0] or epoch,"token_expires_at":_time(upstream.get("token_expires_at"))[0] or one,"token_ttl_seconds":upstream.get("token_ttl_seconds") if isinstance(upstream.get("token_ttl_seconds"),int) and not isinstance(upstream.get("token_ttl_seconds"),bool) and upstream.get("token_ttl_seconds")>0 else 1,
      "authorization_token_preparation_id":_text(upstream.get("authorization_token_preparation_id")),"authorization_token_preparation_fingerprint":_text(upstream.get("authorization_token_preparation_fingerprint")),"authorization_token_eligibility_id":_text(upstream.get("authorization_token_eligibility_id")),"authorization_token_eligibility_fingerprint":_text(upstream.get("authorization_token_eligibility_fingerprint")),
      "active_authorization_id":_text(upstream.get("active_authorization_id")),"active_authorization_fingerprint":_text(upstream.get("active_authorization_fingerprint")),"authorized_at":_time(upstream.get("authorized_at"))[0] or epoch,"authorization_expires_at":_time(upstream.get("authorization_expires_at"))[0] or one,"authorization_ttl_seconds":upstream.get("authorization_ttl_seconds") if isinstance(upstream.get("authorization_ttl_seconds"),int) and not isinstance(upstream.get("authorization_ttl_seconds"),bool) and upstream.get("authorization_ttl_seconds")>0 else 1,
      "issuance_preparation_created":status=="prepared",**{n:False for n in _FLAGS},"reasons":sorted(set(reasons)),"errors":sorted(set(errors))}
    for x in _LINEAGES: base[x+"_id"]=_text(upstream.get(x+"_id")); base[x+"_fingerprint"]=_text(upstream.get(x+"_fingerprint"))
    f=_hash(base); base["preparation_id"]="capability-authorization-token-issuance-preparation-"+f[:24]; base["fingerprint"]=f
    result=json.loads(canonical_json(base))
    from core.runtime.runtime_capability_authorization_token_issuance_preparation_validation import validate_capability_authorization_token_issuance_preparation
    if not validate_capability_authorization_token_issuance_preparation(result).valid: raise RuntimeError("internal issuance preparation validation failed")
    return result

__all__=["CAPABILITY_AUTHORIZATION_TOKEN_ISSUANCE_PREPARATION_SCHEMA","TOKEN_ISSUANCE_PREPARATION_STATUSES","prepare_capability_authorization_token_issuance"]
