from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_dry_run_dispatch_result import *
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityDryRunDispatchResultValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"contract","schema_version","dispatch_result_id","dispatch_result_fingerprint","dispatch_plan_id","dispatch_plan_fingerprint","adapter_admission_id","adapter_admission_fingerprint","request_id","request_fingerprint","adapter_id","operation_class","observed_status","result_status","simulated","side_effects_performed","observation_summary","evidence_references","failure_reasons","blocked_reasons"}
def validate_capability_dry_run_dispatch_result(v:Any)->CapabilityDryRunDispatchResultValidationResult:
 if not isinstance(v,Mapping):return CapabilityDryRunDispatchResultValidationResult(False,("result_not_object",))
 e=[];s=v.get("result_status")
 if set(v)!=_REQ:e.append("invalid_fields")
 if v.get("contract")!=CONTRACT or v.get("schema_version")!=SCHEMA_VERSION:e.append("invalid_contract")
 if s not in STATUSES or v.get("observed_status") not in OBSERVED or v.get("simulated") is not(s=="simulated"):e.append("invalid_status")
 if v.get("side_effects_performed")!=[]:e.append("side_effect_invariant")
 try:
  f=_hash({k:x for k,x in v.items() if k not in {"dispatch_result_id","dispatch_result_fingerprint"}})
  if v.get("dispatch_result_fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("dispatch_result_id")!="capability-dry-run-dispatch-result-"+f[:24]:e.append("id_mismatch")
 except (TypeError,ValueError):e.append("noncanonical_value")
 return CapabilityDryRunDispatchResultValidationResult(not e,tuple(dict.fromkeys(e)))
