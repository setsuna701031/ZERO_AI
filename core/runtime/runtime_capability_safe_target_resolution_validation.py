from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_safe_target_resolution import *
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilitySafeTargetResolutionValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"contract","schema_version","target_resolution_id","target_resolution_fingerprint","read_only_admission_id","read_only_admission_fingerprint","observation_request_id","observation_request_fingerprint","workspace_root_canonical","relative_target","resolved_target_canonical","target_exists","target_type","target_size_bytes","symlink_or_reparse_detected","containment_verified","resolution_status","reasons","blocked_reasons","failure_reasons"}
def validate_capability_safe_target_resolution(v:Any)->CapabilitySafeTargetResolutionValidationResult:
 if not isinstance(v,Mapping):return CapabilitySafeTargetResolutionValidationResult(False,("resolution_not_object",))
 e=[]
 if set(v)!=_REQ:e.append("invalid_fields")
 if v.get("contract")!=CONTRACT or v.get("schema_version")!=SCHEMA_VERSION or v.get("resolution_status") not in STATUSES:e.append("invalid_contract_or_status")
 if v.get("resolution_status")=="resolved" and (v.get("containment_verified") is not True or v.get("symlink_or_reparse_detected") is not False or v.get("target_type") not in {"regular_file","directory","other"}):e.append("forbidden_success_transition")
 try:f=_hash({k:x for k,x in v.items() if k not in {"target_resolution_id","target_resolution_fingerprint"}})
 except (TypeError,ValueError):e.append("noncanonical_value")
 else:
  if v.get("target_resolution_fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("target_resolution_id")!="capability-safe-target-resolution-"+f[:24]:e.append("id_mismatch")
 return CapabilitySafeTargetResolutionValidationResult(not e,tuple(dict.fromkeys(e)))
