from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_read_only_adapter_admission import *
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityReadOnlyAdapterAdmissionValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"contract","schema_version","read_only_admission_id","read_only_admission_fingerprint","authority_id","authority_fingerprint","request_id","request_fingerprint","bridge_closure_id","bridge_closure_fingerprint","adapter_id","adapter_kind","adapter_mode","workspace_root_descriptor","allowed_observation_kinds","adapter_capabilities","admission_status","admitted","reasons","blocked_reasons"}
def validate_capability_read_only_adapter_admission(v:Any)->CapabilityReadOnlyAdapterAdmissionValidationResult:
 if not isinstance(v,Mapping):return CapabilityReadOnlyAdapterAdmissionValidationResult(False,("admission_not_object",))
 e=[];s=v.get("admission_status")
 if set(v)!=_REQ:e.append("invalid_fields")
 if v.get("contract")!=CONTRACT or v.get("schema_version")!=SCHEMA_VERSION:e.append("invalid_contract")
 if s not in STATUSES or v.get("admitted") is not(s=="admitted"):e.append("invalid_status")
 if s=="admitted" and (v.get("adapter_kind")!="bounded_read_only_observation_adapter" or v.get("adapter_mode")!="read_only" or v.get("adapter_capabilities")!=CAPABILITIES):e.append("forbidden_success_transition")
 try:f=_hash({k:x for k,x in v.items() if k not in {"read_only_admission_id","read_only_admission_fingerprint"}})
 except (TypeError,ValueError):e.append("noncanonical_value")
 else:
  if v.get("read_only_admission_fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("read_only_admission_id")!="capability-read-only-adapter-admission-"+f[:24]:e.append("id_mismatch")
 return CapabilityReadOnlyAdapterAdmissionValidationResult(not e,tuple(dict.fromkeys(e)))
