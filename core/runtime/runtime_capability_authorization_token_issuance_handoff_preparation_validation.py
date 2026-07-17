from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any,Mapping
from core.runtime.runtime_capability_authorization_token_issuance import MAX_ISSUANCE_TTL_SECONDS
from core.runtime.runtime_capability_authorization_token_issuance_handoff_preparation import *
from core.runtime.runtime_capability_authorization_token_issuance_handoff_preparation import _LINEAGES,_FLAGS,_FORBIDDEN,_hash
@dataclass(frozen=True)
class CapabilityAuthorizationTokenIssuanceHandoffPreparationValidationResult:valid:bool;errors:tuple[str,...]
_BASE={"schema","handoff_preparation_id","status",*HANDOFF_PREPARATION_STATUSES,"prepared_at","token_issuance_id","token_issuance_fingerprint","token_issuance_status","issued_at","issuance_expires_at","issuance_ttl_seconds","token_issuance_preparation_id","token_issuance_preparation_fingerprint","token_issuance_eligibility_id","token_issuance_eligibility_fingerprint","authorization_token_id","authorization_token_fingerprint","authorization_token_preparation_id","authorization_token_preparation_fingerprint","authorization_token_eligibility_id","authorization_token_eligibility_fingerprint","active_authorization_id","active_authorization_fingerprint","token_created_at","token_expires_at","authorized_at","authorization_expires_at","handoff_preparation_created",*_FLAGS,"reasons","errors","fingerprint"};_REQ=_BASE|{z+s for z in _LINEAGES for s in ("_id","_fingerprint")}
def validate_capability_authorization_token_issuance_handoff_preparation(v:Any)->CapabilityAuthorizationTokenIssuanceHandoffPreparationValidationResult:
 if not isinstance(v,Mapping):return CapabilityAuthorizationTokenIssuanceHandoffPreparationValidationResult(False,("handoff_preparation_not_object",))
 e=[];k=set(v);s=v.get("status")
 if k!=_REQ:e.append("invalid_fields")
 if k&_FORBIDDEN:e.append("forged_authority_field")
 if v.get("schema")!=CAPABILITY_AUTHORIZATION_TOKEN_ISSUANCE_HANDOFF_PREPARATION_SCHEMA:e.append("invalid_schema")
 if s not in HANDOFF_PREPARATION_STATUSES:e.append("invalid_status")
 if any(v.get(n) is not(n==s) for n in HANDOFF_PREPARATION_STATUSES):e.append("inconsistent_status_flags")
 ts={}
 for n in ("prepared_at","issued_at","issuance_expires_at","token_created_at","token_expires_at","authorized_at","authorization_expires_at"):
  try:p=datetime.fromisoformat(v.get(n,"").replace("Z","+00:00"));assert p.tzinfo is not None and p.utcoffset() is not None;ts[n]=p
  except (ValueError,TypeError,AttributeError,AssertionError):e.append("invalid_"+n)
 t=v.get("issuance_ttl_seconds")
 if not isinstance(t,int) or isinstance(t,bool) or not 0<t<=MAX_ISSUANCE_TTL_SECONDS:e.append("invalid_issuance_ttl")
 elif "issued_at" in ts and "issuance_expires_at" in ts and (ts["issuance_expires_at"]-ts["issued_at"]).total_seconds()!=t:e.append("issuance_ttl_mismatch")
 for z in ("token_issuance","token_issuance_preparation","token_issuance_eligibility","authorization_token","authorization_token_preparation","authorization_token_eligibility","active_authorization")+_LINEAGES:
  if not all(isinstance(v.get(z+x),str) and v.get(z+x) for x in ("_id","_fingerprint")):e.append("missing_linkage")
 if v.get("handoff_preparation_created") is not(s=="prepared"):e.append("inconsistent_preparation")
 if any(v.get(n) is not False for n in _FLAGS):e.append("handoff_state_violation")
 for n in ("reasons","errors"):
  z=v.get(n)
  if not isinstance(z,list) or z!=sorted(set(z)) or any(not isinstance(c,str) or not re.fullmatch(r"[a-z0-9_]{1,128}",c) for c in z):e.append("invalid_"+n)
 try:
  f=_hash({a:b for a,b in v.items() if a not in {"handoff_preparation_id","fingerprint"}})
  if v.get("fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("handoff_preparation_id")!="capability-authorization-token-issuance-handoff-preparation-"+f[:24]:e.append("handoff_preparation_id_mismatch")
 except (TypeError,ValueError):e.append("noncanonical_value")
 return CapabilityAuthorizationTokenIssuanceHandoffPreparationValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["CapabilityAuthorizationTokenIssuanceHandoffPreparationValidationResult","validate_capability_authorization_token_issuance_handoff_preparation"]
