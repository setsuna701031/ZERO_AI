from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_executor_adapter_admission import *
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityExecutorAdapterAdmissionValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"contract","schema_version","adapter_admission_id","adapter_admission_fingerprint","authority_id","authority_fingerprint","request_id","request_fingerprint","adapter_id","adapter_kind","adapter_mode","supported_operation_classes","adapter_capabilities","admission_status","admitted","reasons","blocked_reasons"}
def validate_capability_executor_adapter_admission(v:Any)->CapabilityExecutorAdapterAdmissionValidationResult:
 if not isinstance(v,Mapping):return CapabilityExecutorAdapterAdmissionValidationResult(False,("admission_not_object",))
 e=[];s=v.get("admission_status");caps=v.get("adapter_capabilities")
 if set(v)!=_REQ:e.append("invalid_fields")
 if v.get("contract")!=CONTRACT or v.get("schema_version")!=SCHEMA_VERSION:e.append("invalid_contract")
 if s not in STATUSES or v.get("admitted") is not(s=="admitted"):e.append("invalid_status")
 if s=="admitted" and (v.get("adapter_kind")!="declarative_executor_adapter" or v.get("adapter_mode")!="dry_run" or not isinstance(caps,Mapping) or set(caps)!=set(CAPABILITY_NAMES) or any(caps.get(n) is not False for n in CAPABILITY_NAMES)):e.append("forbidden_success_transition")
 try:
  f=_hash({k:x for k,x in v.items() if k not in {"adapter_admission_id","adapter_admission_fingerprint"}})
  if v.get("adapter_admission_fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("adapter_admission_id")!="capability-executor-adapter-admission-"+f[:24]:e.append("id_mismatch")
 except (TypeError,ValueError):e.append("noncanonical_value")
 return CapabilityExecutorAdapterAdmissionValidationResult(not e,tuple(dict.fromkeys(e)))
