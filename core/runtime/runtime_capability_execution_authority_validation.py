from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_execution_authority import *
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityExecutionAuthorityValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"schema","authority_id","fingerprint","status","session_admission_id","session_admission_fingerprint","issued_scope","authority_constraints","issued_at","expires_at","denied_reasons","blocked_reasons"}
def validate_capability_execution_authority(v:Any)->CapabilityExecutionAuthorityValidationResult:
    if not isinstance(v,Mapping):return CapabilityExecutionAuthorityValidationResult(False,("authority_not_object",))
    e=[];c=v.get("authority_constraints")
    if set(v)!=_REQ:e.append("invalid_fields")
    if v.get("schema")!=CAPABILITY_EXECUTION_AUTHORITY_SCHEMA:e.append("invalid_schema")
    if v.get("status") not in EXECUTION_AUTHORITY_STATUSES:e.append("invalid_status")
    if not isinstance(c,Mapping):e.append("invalid_constraints")
    else:
        if not isinstance(c.get("maximum_request_count"),int) or isinstance(c.get("maximum_request_count"),bool) or c.get("maximum_request_count",0)<1:e.append("invalid_request_limit")
        if not isinstance(c.get("allowed_operation_classes"),list) or not set(c.get("allowed_operation_classes",[]))<=SAFE_OPERATION_CLASSES:e.append("invalid_operation_classes")
        if any(c.get(n) is not False for n in ("mutation_permission","external_process_permission","network_permission","model_invocation_permission")) and v.get("status")!="blocked":e.append("forbidden_success_transition")
    try:
        f=_hash({k:x for k,x in v.items() if k not in {"authority_id","fingerprint"}})
        if v.get("fingerprint")!=f:e.append("fingerprint_mismatch")
        if v.get("authority_id")!="capability-execution-authority-"+f[:24]:e.append("authority_id_mismatch")
    except (TypeError,ValueError):e.append("noncanonical_value")
    return CapabilityExecutionAuthorityValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["CapabilityExecutionAuthorityValidationResult","validate_capability_execution_authority"]
