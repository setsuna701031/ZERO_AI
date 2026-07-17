from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any,Mapping
from core.runtime.runtime_capability_authorization_token_issuance import *
from core.runtime.runtime_capability_authorization_token_issuance import _LINEAGES,_FLAGS,_FORBIDDEN,_hash
@dataclass(frozen=True)
class CapabilityAuthorizationTokenIssuanceValidationResult:valid:bool;errors:tuple[str,...]
_BASE={"schema","issuance_id","status",*TOKEN_ISSUANCE_STATUSES,"issued_at","issuance_expires_at","issuance_ttl_seconds","token_issuance_preparation_id","token_issuance_preparation_fingerprint","token_issuance_preparation_status","issuance_prepared_at","token_issuance_eligibility_id","token_issuance_eligibility_fingerprint","authorization_token_id","authorization_token_fingerprint","authorization_token_preparation_id","authorization_token_preparation_fingerprint","authorization_token_eligibility_id","authorization_token_eligibility_fingerprint","active_authorization_id","active_authorization_fingerprint","token_created_at","token_expires_at","token_ttl_seconds","authorized_at","authorization_expires_at","authorization_ttl_seconds","issuance_record_created","token_issued",*_FLAGS,"reasons","errors","fingerprint"};_REQ=_BASE|{z+s for z in _LINEAGES for s in ("_id","_fingerprint")}
def validate_capability_authorization_token_issuance(v:Any)->CapabilityAuthorizationTokenIssuanceValidationResult:
 if not isinstance(v,Mapping):return CapabilityAuthorizationTokenIssuanceValidationResult(False,("issuance_not_object",))
 e=[];k=set(v);s=v.get("status")
 if k!=_REQ:e.append("invalid_fields")
 if k&_FORBIDDEN:e.append("forged_authority_field")
 if v.get("schema")!=CAPABILITY_AUTHORIZATION_TOKEN_ISSUANCE_SCHEMA:e.append("invalid_schema")
 if s not in TOKEN_ISSUANCE_STATUSES:e.append("invalid_status")
 if any(v.get(n) is not(n==s) for n in TOKEN_ISSUANCE_STATUSES):e.append("inconsistent_status_flags")
 ts={}
 for n in ("issued_at","issuance_expires_at","issuance_prepared_at","token_created_at","token_expires_at","authorized_at","authorization_expires_at"):
  try:p=datetime.fromisoformat(v.get(n,"").replace("Z","+00:00"));assert p.tzinfo is not None and p.utcoffset() is not None;ts[n]=p
  except (ValueError,TypeError,AttributeError,AssertionError):e.append("invalid_"+n)
 for a,b,c,m in (("issued_at","issuance_expires_at","issuance_ttl_seconds",MAX_ISSUANCE_TTL_SECONDS),("token_created_at","token_expires_at","token_ttl_seconds",300),("authorized_at","authorization_expires_at","authorization_ttl_seconds",999999)):
  t=v.get(c)
  if not isinstance(t,int) or isinstance(t,bool) or not 0<t<=m:e.append("invalid_"+c)
  elif a in ts and b in ts and (ts[b]-ts[a]).total_seconds()!=t:e.append(c+"_mismatch")
 if s=="issued" and all(n in ts for n in ("issuance_expires_at","token_expires_at","authorization_expires_at")) and ts["issuance_expires_at"]>min(ts["token_expires_at"],ts["authorization_expires_at"]):e.append("issuance_expiry_exceeds_upstream")
 for z in ("token_issuance_preparation","token_issuance_eligibility","authorization_token","authorization_token_preparation","authorization_token_eligibility","active_authorization")+_LINEAGES:
  if not all(isinstance(v.get(z+x),str) and v.get(z+x) for x in ("_id","_fingerprint")):e.append("missing_linkage")
 if v.get("issuance_record_created") is not(s=="issued") or v.get("token_issued") is not(s=="issued"):e.append("inconsistent_issuance")
 if any(v.get(n) is not False for n in _FLAGS):e.append("issuance_state_violation")
 for n in ("reasons","errors"):
  z=v.get(n)
  if not isinstance(z,list) or z!=sorted(set(z)) or any(not isinstance(c,str) or not re.fullmatch(r"[a-z0-9_]{1,128}",c) for c in z):e.append("invalid_"+n)
 try:
  f=_hash({a:b for a,b in v.items() if a not in {"issuance_id","fingerprint"}})
  if v.get("fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("issuance_id")!="capability-authorization-token-issuance-"+f[:24]:e.append("issuance_id_mismatch")
 except (TypeError,ValueError):e.append("noncanonical_value")
 return CapabilityAuthorizationTokenIssuanceValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["CapabilityAuthorizationTokenIssuanceValidationResult","validate_capability_authorization_token_issuance"]
