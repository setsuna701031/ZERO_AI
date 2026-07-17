from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_runtime_outcome_reconciliation import *
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityRuntimeOutcomeReconciliationValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"contract","schema_version","reconciliation_id","reconciliation_fingerprint","authority_id","authority_fingerprint","request_id","request_fingerprint","adapter_admission_id","adapter_admission_fingerprint","dispatch_plan_id","dispatch_plan_fingerprint","dispatch_result_id","dispatch_result_fingerprint","adapter_id","operation_class","bridge_status","execution_completion_claim","recommended_v1_2_outcome_status","reconciliation_status","evidence_references","reasons","blocked_reasons","failure_reasons"}
def validate_capability_runtime_outcome_reconciliation(v:Any)->CapabilityRuntimeOutcomeReconciliationValidationResult:
 if not isinstance(v,Mapping):return CapabilityRuntimeOutcomeReconciliationValidationResult(False,("reconciliation_not_object",))
 e=[];s=v.get("reconciliation_status")
 if set(v)!=_REQ:e.append("invalid_fields")
 if v.get("contract")!=CONTRACT or v.get("schema_version")!=SCHEMA_VERSION:e.append("invalid_contract")
 if s not in STATUSES or v.get("execution_completion_claim") is not False or (v.get("bridge_status")=="simulated" and v.get("recommended_v1_2_outcome_status")!="not_completed"):e.append("forbidden_completion_claim")
 try:
  f=_hash({k:x for k,x in v.items() if k not in {"reconciliation_id","reconciliation_fingerprint"}})
  if v.get("reconciliation_fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("reconciliation_id")!="capability-runtime-outcome-reconciliation-"+f[:24]:e.append("id_mismatch")
 except (TypeError,ValueError):e.append("noncanonical_value")
 return CapabilityRuntimeOutcomeReconciliationValidationResult(not e,tuple(dict.fromkeys(e)))
