
from __future__ import annotations
import hashlib, json, os
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Mapping
try:
 from core.engineering.engineering_runtime_adapter_execution_integration_common import canonical_fingerprint
except Exception:
 def canonical_fingerprint(v:Any)->str:
  return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
ADAPTER_ID='zero.engineering.read_only_workspace'; ADAPTER_VERSION='1'; EXECUTION_MODE='synchronous_bounded_local_read'
OPERATIONS=('workspace_exists','path_exists','path_kind','list_directory','read_text','file_sha256','file_metadata')
KINDS=('missing','file','directory','symlink','other')
FAILURE_CODES={'workspace_not_admitted','workspace_missing','workspace_not_directory','path_invalid','path_outside_workspace','path_missing','path_not_file','path_not_directory','symlink_disallowed','operation_not_allowed','permission_denied','file_too_large','directory_entry_limit_exceeded','invalid_utf8','unsupported_path_kind','read_failed','metadata_failed','hash_failed','cancellation_requested','linkage_invalid','invariant_violation'}
def stable_id(prefix:str, body:Mapping[str,Any])->str: return prefix+'-'+canonical_fingerprint(body)[:24]
def canon(body:dict[str,Any], id_field:str|None=None, prefix:str='id')->dict[str,Any]:
 b=dict(body); b['fingerprint']=canonical_fingerprint(b)
 if id_field: b[id_field]=prefix+'-'+b['fingerprint'][:24]
 return b


from core.engineering.engineering_runtime_workspace_path_resolution import resolve_workspace_path
from core.engineering.engineering_runtime_workspace_read_scope import validate_scope_request
SCHEMA='zero.engineering.runtime_workspace_execution_preflight.v1'
def build_workspace_execution_preflight(submission, registry, admission, read_scope):
 reasons=[]; descriptor=registry.descriptor(submission.get('adapter_id'),submission.get('adapter_version')) if registry else None
 if descriptor is None: reasons.append('linkage_invalid')
 adapter=registry.lookup(submission.get('adapter_id'),submission.get('adapter_version')) if registry else None
 if adapter is None: reasons.append('linkage_invalid')
 if not admission.get('admitted'): reasons.append('workspace_not_admitted')
 ok,errs=validate_scope_request(read_scope, submission.get('operation'), submission.get('relative_path',''), submission.get('operation_parameters') or {}); reasons+=errs
 path_art,_=resolve_workspace_path(admission, submission.get('relative_path',''), allow_root=submission.get('operation') in ('workspace_exists','list_directory'), allow_symlinks=read_scope.get('allow_symlinks',False)); reasons += [r for r in path_art['reason_codes'] if r!='resolved']
 if (submission.get('cancellation_state') or {}).get('cancelled'): reasons.append('cancellation_requested')
 if any(submission.get('authority_constraints',{}).values()): reasons.append('authority_expansion')
 body={'schema':SCHEMA,'submission_id':submission.get('submission_id'),'registry_fingerprint':registry.snapshot().get('fingerprint') if registry else None,'descriptor_fingerprint':descriptor.get('fingerprint') if descriptor else None,'admission_id':admission.get('admission_id'),'read_scope_id':read_scope.get('scope_id'),'path_resolution_id':path_art.get('path_resolution_id'),'preflight_status':'passed' if not reasons else ('cancelled' if 'cancellation_requested' in reasons else 'rejected'),'adapter_invocation_allowed':not reasons,'reason_codes':sorted(set(reasons)) or ['passed']}
 return canon(body,'preflight_id','pfl'), path_art
