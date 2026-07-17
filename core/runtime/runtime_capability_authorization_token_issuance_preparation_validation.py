from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any,Mapping
from core.runtime.runtime_capability_authorization_token import MAX_TOKEN_TTL_SECONDS
from core.runtime.runtime_capability_authorization_token_issuance_preparation import CAPABILITY_AUTHORIZATION_TOKEN_ISSUANCE_PREPARATION_SCHEMA,TOKEN_ISSUANCE_PREPARATION_STATUSES,_LINEAGES,_FLAGS,_FORBIDDEN,_hash
@dataclass(frozen=True)
class CapabilityAuthorizationTokenIssuancePreparationValidationResult: valid:bool; errors:tuple[str,...]
_BASE={"schema","preparation_id","status",*TOKEN_ISSUANCE_PREPARATION_STATUSES,"prepared_at","token_issuance_eligibility_id","token_issuance_eligibility_fingerprint","token_issuance_eligibility_status","issuance_eligibility_evaluated_at","authorization_token_id","authorization_token_fingerprint","authorization_token_status","token_created_at","token_expires_at","token_ttl_seconds","authorization_token_preparation_id","authorization_token_preparation_fingerprint","authorization_token_eligibility_id","authorization_token_eligibility_fingerprint","active_authorization_id","active_authorization_fingerprint","authorized_at","authorization_expires_at","authorization_ttl_seconds","issuance_preparation_created",*_FLAGS,"reasons","errors","fingerprint"}
_REQ=_BASE|{x+s for x in _LINEAGES for s in ("_id","_fingerprint")}
def validate_capability_authorization_token_issuance_preparation(v:Any)->CapabilityAuthorizationTokenIssuancePreparationValidationResult:
    if not isinstance(v,Mapping): return CapabilityAuthorizationTokenIssuancePreparationValidationResult(False,("preparation_not_object",))
    e=[]; keys=set(v); s=v.get("status")
    if keys!=_REQ:e.append("invalid_fields")
    if keys&_FORBIDDEN:e.append("forged_authority_field")
    if v.get("schema")!=CAPABILITY_AUTHORIZATION_TOKEN_ISSUANCE_PREPARATION_SCHEMA:e.append("invalid_schema")
    if s not in TOKEN_ISSUANCE_PREPARATION_STATUSES:e.append("invalid_status")
    if any(v.get(n) is not(n==s) for n in TOKEN_ISSUANCE_PREPARATION_STATUSES):e.append("inconsistent_status_flags")
    ts={}
    for n in ("prepared_at","issuance_eligibility_evaluated_at","token_created_at","token_expires_at","authorized_at","authorization_expires_at"):
        try: p=datetime.fromisoformat(v.get(n,"").replace("Z","+00:00")); assert p.tzinfo is not None and p.utcoffset() is not None; ts[n]=p
        except (AttributeError,ValueError,TypeError,AssertionError):e.append("invalid_"+n)
    tt=v.get("token_ttl_seconds"); at=v.get("authorization_ttl_seconds")
    if not isinstance(tt,int) or isinstance(tt,bool) or not 0<tt<=MAX_TOKEN_TTL_SECONDS:e.append("invalid_token_ttl")
    if not isinstance(at,int) or isinstance(at,bool) or at<=0:e.append("invalid_authorization_ttl")
    if all(n in ts for n in ("token_created_at","token_expires_at")) and isinstance(tt,int) and not isinstance(tt,bool) and (ts["token_expires_at"]-ts["token_created_at"]).total_seconds()!=tt:e.append("token_ttl_mismatch")
    if all(n in ts for n in ("authorized_at","authorization_expires_at")) and isinstance(at,int) and not isinstance(at,bool) and (ts["authorization_expires_at"]-ts["authorized_at"]).total_seconds()!=at:e.append("authorization_ttl_mismatch")
    for x in ("token_issuance_eligibility","authorization_token","authorization_token_preparation","authorization_token_eligibility","active_authorization")+_LINEAGES:
        if not all(isinstance(v.get(x+y),str) and v.get(x+y) for y in ("_id","_fingerprint")):e.append("missing_linkage")
    if v.get("issuance_preparation_created") is not(s=="prepared"):e.append("inconsistent_preparation")
    if any(v.get(n) is not False for n in _FLAGS):e.append("issuance_state_violation")
    for n in ("reasons","errors"):
        z=v.get(n)
        if not isinstance(z,list) or z!=sorted(set(z)) or any(not isinstance(c,str) or not re.fullmatch(r"[a-z0-9_]{1,128}",c) for c in z):e.append("invalid_"+n)
    try:
        f=_hash({k:x for k,x in v.items() if k not in {"preparation_id","fingerprint"}})
        if v.get("fingerprint")!=f:e.append("fingerprint_mismatch")
        if v.get("preparation_id")!="capability-authorization-token-issuance-preparation-"+f[:24]:e.append("preparation_id_mismatch")
    except (TypeError,ValueError):e.append("noncanonical_value")
    return CapabilityAuthorizationTokenIssuancePreparationValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["CapabilityAuthorizationTokenIssuancePreparationValidationResult","validate_capability_authorization_token_issuance_preparation"]
