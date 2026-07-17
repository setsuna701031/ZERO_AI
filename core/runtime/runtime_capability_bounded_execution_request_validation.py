from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_bounded_execution_request import *
from core.runtime.runtime_capability_execution_authority import SAFE_OPERATION_CLASSES
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityBoundedExecutionRequestValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"schema","request_id","fingerprint","status","authority_id","authority_fingerprint","operation_class","target_descriptor","bounded_parameters","request_ordinal","acceptance_reasons","rejection_reasons","blocked_reasons"}
def validate_capability_bounded_execution_request(v:Any)->CapabilityBoundedExecutionRequestValidationResult:
    if not isinstance(v,Mapping):return CapabilityBoundedExecutionRequestValidationResult(False,("request_not_object",))
    e=[]
    if set(v)!=_REQ:e.append("invalid_fields")
    if v.get("schema")!=CAPABILITY_BOUNDED_EXECUTION_REQUEST_SCHEMA:e.append("invalid_schema")
    if v.get("status") not in BOUNDED_EXECUTION_REQUEST_STATUSES:e.append("invalid_status")
    if v.get("operation_class") not in SAFE_OPERATION_CLASSES and v.get("status")!="blocked":e.append("forbidden_success_transition")
    if (not isinstance(v.get("request_ordinal"),int) or isinstance(v.get("request_ordinal"),bool) or v.get("request_ordinal",0)<1) and v.get("status")!="invalid":e.append("invalid_request_ordinal")
    try:
        f=_hash({k:x for k,x in v.items() if k not in {"request_id","fingerprint"}})
        if v.get("fingerprint")!=f:e.append("fingerprint_mismatch")
        if v.get("request_id")!="capability-bounded-execution-request-"+f[:24]:e.append("request_id_mismatch")
    except (TypeError,ValueError):e.append("noncanonical_value")
    return CapabilityBoundedExecutionRequestValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["CapabilityBoundedExecutionRequestValidationResult","validate_capability_bounded_execution_request"]
