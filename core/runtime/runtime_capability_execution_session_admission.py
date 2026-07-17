from __future__ import annotations
import hashlib,json
from copy import deepcopy
from typing import Any,Mapping

CAPABILITY_EXECUTION_SESSION_ADMISSION_SCHEMA="zero.runtime.capability_execution_session_admission.v1"
EXECUTION_SESSION_ADMISSION_STATUSES=frozenset({"admitted","not_admitted","blocked","invalid"})

def _safe(v:Any)->Any:
    v=deepcopy(v)
    json.dumps(v,allow_nan=False)
    return v
def _hash(v:Any)->str:return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def _identity(base:dict[str,Any],field:str,prefix:str)->dict[str,Any]:
    f=_hash(base);return {**base,field:f"{prefix}{f[:24]}","fingerprint":f}
def _link(v:Mapping[str,Any],stem:str)->tuple[str,str]:return (v.get(stem+"_id","") if isinstance(v.get(stem+"_id"),str) else "",v.get(stem+"_fingerprint","") if isinstance(v.get(stem+"_fingerprint"),str) else "")

def admit_capability_execution_session(activation_verification_closure:Any,*,capability_profile_id:Any="",capability_strategy_id:Any="")->dict[str,Any]:
    u=deepcopy(dict(activation_verification_closure)) if isinstance(activation_verification_closure,Mapping) else {}
    valid=isinstance(u.get("closure_id"),str) and bool(u.get("closure_id")) and isinstance(u.get("fingerprint"),str) and len(u.get("fingerprint"))==64
    state=u.get("status");closed=u.get("activation_audit_closed") is True or u.get("closed") is True
    if not isinstance(activation_verification_closure,Mapping):status="invalid";reasons=["malformed_activation_verification_closure"]
    elif not valid:status="invalid";reasons=["invalid_activation_verification_closure"]
    elif state in {"blocked","failed","invalid","expired"}:status="blocked";reasons=["activation_verification_"+state]
    elif state not in {"verified","verified_closed"} or not closed:status="not_admitted";reasons=["activation_not_verified_closed"]
    else:status="admitted";reasons=["activation_verified_closed"]
    base={"schema":CAPABILITY_EXECUTION_SESSION_ADMISSION_SCHEMA,"status":status,"activation_verification_closure_id":u.get("closure_id","") if isinstance(u.get("closure_id"),str) else "","activation_verification_closure_fingerprint":u.get("fingerprint","") if isinstance(u.get("fingerprint"),str) else "","capability_profile_id":capability_profile_id if isinstance(capability_profile_id,str) else "","capability_strategy_id":capability_strategy_id if isinstance(capability_strategy_id,str) else "","reasons":sorted(set(reasons))}
    return _identity(base,"session_admission_id","capability-execution-session-admission-")

build_capability_execution_session_admission=admit_capability_execution_session
__all__=["CAPABILITY_EXECUTION_SESSION_ADMISSION_SCHEMA","EXECUTION_SESSION_ADMISSION_STATUSES","admit_capability_execution_session","build_capability_execution_session_admission"]
