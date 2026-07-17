from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_dry_run_dispatch_plan import *
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityDryRunDispatchPlanValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"contract","schema_version","dispatch_plan_id","dispatch_plan_fingerprint","adapter_admission_id","adapter_admission_fingerprint","authority_id","authority_fingerprint","request_id","request_fingerprint","adapter_id","adapter_mode","operation_class","target_descriptor","bounded_parameters","dispatch_ordinal","dry_run","expected_effects","prohibited_effects","plan_status","reasons","blocked_reasons"}
def validate_capability_dry_run_dispatch_plan(v:Any)->CapabilityDryRunDispatchPlanValidationResult:
 if not isinstance(v,Mapping):return CapabilityDryRunDispatchPlanValidationResult(False,("plan_not_object",))
 e=[];s=v.get("plan_status")
 if set(v)!=_REQ:e.append("invalid_fields")
 if v.get("contract")!=CONTRACT or v.get("schema_version")!=SCHEMA_VERSION:e.append("invalid_contract")
 if s not in STATUSES:e.append("invalid_status")
 if not isinstance(v.get("dispatch_ordinal"),int) or isinstance(v.get("dispatch_ordinal"),bool) or v.get("dispatch_ordinal",-1)<0:e.append("invalid_ordinal")
 if v.get("dry_run") is not True or v.get("expected_effects")!=[] or v.get("prohibited_effects")!=PROHIBITED_EFFECTS or (s=="planned" and v.get("adapter_mode")!="dry_run"):e.append("dry_run_invariant")
 try:
  f=_hash({k:x for k,x in v.items() if k not in {"dispatch_plan_id","dispatch_plan_fingerprint"}})
  if v.get("dispatch_plan_fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("dispatch_plan_id")!="capability-dry-run-dispatch-plan-"+f[:24]:e.append("id_mismatch")
 except (TypeError,ValueError):e.append("noncanonical_value")
 return CapabilityDryRunDispatchPlanValidationResult(not e,tuple(dict.fromkeys(e)))
