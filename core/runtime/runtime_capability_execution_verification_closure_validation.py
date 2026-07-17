from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_execution_verification_closure import *
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityExecutionVerificationClosureValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"schema","closure_id","fingerprint","status","session_admission_id","session_admission_fingerprint","authority_id","authority_fingerprint","request_id","request_fingerprint","outcome_id","outcome_fingerprint","chain_validation_results","evidence_reference_validation_results","closed","reasons"}
def validate_capability_execution_verification_closure(v:Any)->CapabilityExecutionVerificationClosureValidationResult:
    if not isinstance(v,Mapping):return CapabilityExecutionVerificationClosureValidationResult(False,("closure_not_object",))
    e=[]
    if set(v)!=_REQ:e.append("invalid_fields")
    if v.get("schema")!=CAPABILITY_EXECUTION_VERIFICATION_CLOSURE_SCHEMA:e.append("invalid_schema")
    if v.get("status") not in EXECUTION_VERIFICATION_CLOSURE_STATUSES:e.append("invalid_status")
    if v.get("closed") is not (v.get("status")=="verified_closed"):e.append("invalid_closed_state")
    if not isinstance(v.get("chain_validation_results"),list) or any(not isinstance(x,Mapping) or x.get("valid") is not True for x in v.get("chain_validation_results",[])) and v.get("status")=="verified_closed":e.append("invalid_chain")
    try:
        f=_hash({k:x for k,x in v.items() if k not in {"closure_id","fingerprint"}})
        if v.get("fingerprint")!=f:e.append("fingerprint_mismatch")
        if v.get("closure_id")!="capability-execution-verification-closure-"+f[:24]:e.append("closure_id_mismatch")
    except (TypeError,ValueError):e.append("noncanonical_value")
    return CapabilityExecutionVerificationClosureValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["CapabilityExecutionVerificationClosureValidationResult","validate_capability_execution_verification_closure"]
