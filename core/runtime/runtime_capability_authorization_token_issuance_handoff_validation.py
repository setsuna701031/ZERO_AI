from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any,Mapping
from core.runtime.runtime_capability_authorization_token_issuance_handoff import *
from core.runtime.runtime_capability_authorization_token_issuance_handoff import _LINEAGES,_FLAGS,_FORBIDDEN,_hash,_recipient
@dataclass(frozen=True)
class CapabilityAuthorizationTokenIssuanceHandoffValidationResult:valid:bool;errors:tuple[str,...]
_BASE={"schema","handoff_id","status",*TOKEN_ISSUANCE_HANDOFF_STATUSES,"handed_off_at","recipient_id","token_issuance_handoff_preparation_id","token_issuance_handoff_preparation_fingerprint","token_issuance_handoff_preparation_status","handoff_prepared_at","token_issuance_id","token_issuance_fingerprint","token_issuance_preparation_id","token_issuance_preparation_fingerprint","token_issuance_eligibility_id","token_issuance_eligibility_fingerprint","authorization_token_id","authorization_token_fingerprint","authorization_token_preparation_id","authorization_token_preparation_fingerprint","authorization_token_eligibility_id","authorization_token_eligibility_fingerprint","active_authorization_id","active_authorization_fingerprint","issued_at","issuance_expires_at","token_created_at","token_expires_at","authorized_at","authorization_expires_at","handoff_record_created","token_handed_off",*_FLAGS,"reasons","errors","fingerprint"};_REQ=_BASE|{z+s for z in _LINEAGES for s in ("_id","_fingerprint")}
def validate_capability_authorization_token_issuance_handoff(v:Any)->CapabilityAuthorizationTokenIssuanceHandoffValidationResult:
 if not isinstance(v,Mapping):return CapabilityAuthorizationTokenIssuanceHandoffValidationResult(False,("handoff_not_object",))
 e=[];k=set(v);s=v.get("status")
 if k!=_REQ:e.append("invalid_fields")
 if k&_FORBIDDEN:e.append("forged_authority_field")
 if v.get("schema")!=CAPABILITY_AUTHORIZATION_TOKEN_ISSUANCE_HANDOFF_SCHEMA:e.append("invalid_schema")
 if s not in TOKEN_ISSUANCE_HANDOFF_STATUSES:e.append("invalid_status")
 if any(v.get(n) is not(n==s) for n in TOKEN_ISSUANCE_HANDOFF_STATUSES):e.append("inconsistent_status_flags")
 if _recipient(v.get("recipient_id"))!=v.get("recipient_id"):e.append("invalid_recipient_id")
 for n in ("handed_off_at","handoff_prepared_at","issued_at","issuance_expires_at","token_created_at","token_expires_at","authorized_at","authorization_expires_at"):
  try:p=datetime.fromisoformat(v.get(n,"").replace("Z","+00:00"));assert p.tzinfo is not None and p.utcoffset() is not None
  except (ValueError,TypeError,AttributeError,AssertionError):e.append("invalid_"+n)
 for z in ("token_issuance_handoff_preparation","token_issuance","token_issuance_preparation","token_issuance_eligibility","authorization_token","authorization_token_preparation","authorization_token_eligibility","active_authorization")+_LINEAGES:
  if not all(isinstance(v.get(z+x),str) and v.get(z+x) for x in ("_id","_fingerprint")):e.append("missing_linkage")
 if v.get("handoff_record_created") is not(s=="handed_off") or v.get("token_handed_off") is not(s=="handed_off"):e.append("inconsistent_handoff")
 if any(v.get(n) is not False for n in _FLAGS):e.append("handoff_state_violation")
 for n in ("reasons","errors"):
  z=v.get(n)
  if not isinstance(z,list) or z!=sorted(set(z)) or any(not isinstance(c,str) or not re.fullmatch(r"[a-z0-9_]{1,128}",c) for c in z):e.append("invalid_"+n)
 try:
  f=_hash({a:b for a,b in v.items() if a not in {"handoff_id","fingerprint"}})
  if v.get("fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("handoff_id")!="capability-authorization-token-issuance-handoff-"+f[:24]:e.append("handoff_id_mismatch")
 except (TypeError,ValueError):e.append("noncanonical_value")
 return CapabilityAuthorizationTokenIssuanceHandoffValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["CapabilityAuthorizationTokenIssuanceHandoffValidationResult","validate_capability_authorization_token_issuance_handoff"]
