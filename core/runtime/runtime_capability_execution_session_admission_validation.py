from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_execution_session_admission import *
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityExecutionSessionAdmissionValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"schema","session_admission_id","fingerprint","status","activation_verification_closure_id","activation_verification_closure_fingerprint","capability_profile_id","capability_strategy_id","reasons"}
def validate_capability_execution_session_admission(v:Any)->CapabilityExecutionSessionAdmissionValidationResult:
    if not isinstance(v,Mapping):return CapabilityExecutionSessionAdmissionValidationResult(False,("admission_not_object",))
    e=[]
    if set(v)!=_REQ:e.append("invalid_fields")
    if v.get("schema")!=CAPABILITY_EXECUTION_SESSION_ADMISSION_SCHEMA:e.append("invalid_schema")
    if v.get("status") not in EXECUTION_SESSION_ADMISSION_STATUSES:e.append("invalid_status")
    for n in ("activation_verification_closure_id","activation_verification_closure_fingerprint"):
        if not isinstance(v.get(n),str) or not v.get(n):e.append("missing_linkage")
    if not isinstance(v.get("reasons"),list) or v.get("reasons")!=sorted(set(v.get("reasons",[]))):e.append("invalid_reasons")
    try:
        f=_hash({k:x for k,x in v.items() if k not in {"session_admission_id","fingerprint"}})
        if v.get("fingerprint")!=f:e.append("fingerprint_mismatch")
        if v.get("session_admission_id")!="capability-execution-session-admission-"+f[:24]:e.append("session_admission_id_mismatch")
    except (TypeError,ValueError):e.append("noncanonical_value")
    return CapabilityExecutionSessionAdmissionValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["CapabilityExecutionSessionAdmissionValidationResult","validate_capability_execution_session_admission"]
