from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_controlled_execution_outcome import *
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityControlledExecutionOutcomeValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"schema","outcome_id","fingerprint","status","request_id","request_fingerprint","authority_id","authority_fingerprint","observed_status","evidence_references","result_summary","failure_or_blocked_reasons"}
def validate_capability_controlled_execution_outcome(v:Any)->CapabilityControlledExecutionOutcomeValidationResult:
    if not isinstance(v,Mapping):return CapabilityControlledExecutionOutcomeValidationResult(False,("outcome_not_object",))
    e=[]
    if set(v)!=_REQ:e.append("invalid_fields")
    if v.get("schema")!=CAPABILITY_CONTROLLED_EXECUTION_OUTCOME_SCHEMA:e.append("invalid_schema")
    if v.get("status") not in CONTROLLED_EXECUTION_OUTCOME_STATUSES:e.append("invalid_status")
    if v.get("observed_status") not in OBSERVED_EXECUTION_STATUSES:e.append("invalid_observed_status")
    if not isinstance(v.get("evidence_references"),list) or any(not isinstance(x,str) or not x or "\n" in x or "\r" in x for x in v.get("evidence_references",[])):e.append("invalid_evidence_references")
    try:
        f=_hash({k:x for k,x in v.items() if k not in {"outcome_id","fingerprint"}})
        if v.get("fingerprint")!=f:e.append("fingerprint_mismatch")
        if v.get("outcome_id")!="capability-controlled-execution-outcome-"+f[:24]:e.append("outcome_id_mismatch")
    except (TypeError,ValueError):e.append("noncanonical_value")
    return CapabilityControlledExecutionOutcomeValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["CapabilityControlledExecutionOutcomeValidationResult","validate_capability_controlled_execution_outcome"]
