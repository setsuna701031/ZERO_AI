from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_executor_bridge_verification_closure import *
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityExecutorBridgeVerificationClosureValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"contract","schema_version","bridge_closure_id","bridge_closure_fingerprint","authority_id","authority_fingerprint","request_id","request_fingerprint","adapter_admission_id","adapter_admission_fingerprint","dispatch_plan_id","dispatch_plan_fingerprint","dispatch_result_id","dispatch_result_fingerprint","reconciliation_id","reconciliation_fingerprint","controlled_execution_outcome_id","controlled_execution_outcome_fingerprint","execution_verification_closure_id","execution_verification_closure_fingerprint","chain_validation_results","dry_run_invariant_results","side_effect_invariant_results","outcome_consistency_results","verification_status","closed","reasons","blocked_reasons","failure_reasons"}
def validate_capability_executor_bridge_verification_closure(v:Any)->CapabilityExecutorBridgeVerificationClosureValidationResult:
 if not isinstance(v,Mapping):return CapabilityExecutorBridgeVerificationClosureValidationResult(False,("closure_not_object",))
 e=[];s=v.get("verification_status")
 if set(v)!=_REQ:e.append("invalid_fields")
 if v.get("contract")!=CONTRACT or v.get("schema_version")!=SCHEMA_VERSION:e.append("invalid_contract")
 if s not in STATUSES or v.get("closed") is not(s=="verified_closed"):e.append("invalid_status")
 if s=="verified_closed" and any(not isinstance(v.get(n),Mapping) or v[n].get("valid") is not True for n in ("chain_validation_results","dry_run_invariant_results","side_effect_invariant_results","outcome_consistency_results")):e.append("forbidden_success_transition")
 if bool(v.get("controlled_execution_outcome_id"))!=bool(v.get("controlled_execution_outcome_fingerprint")) or bool(v.get("execution_verification_closure_id"))!=bool(v.get("execution_verification_closure_fingerprint")):e.append("malformed_optional_linkage")
 try:
  f=_hash({k:x for k,x in v.items() if k not in {"bridge_closure_id","bridge_closure_fingerprint"}})
  if v.get("bridge_closure_fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("bridge_closure_id")!="capability-executor-bridge-verification-closure-"+f[:24]:e.append("id_mismatch")
 except (TypeError,ValueError):e.append("noncanonical_value")
 return CapabilityExecutorBridgeVerificationClosureValidationResult(not e,tuple(dict.fromkeys(e)))
