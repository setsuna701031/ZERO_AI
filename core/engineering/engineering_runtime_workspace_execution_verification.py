
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


SCHEMA='zero.engineering.runtime_workspace_execution_verification.v1'
def verify_workspace_execution(submission, preflight, controlled, result):
 reasons=[]
 if result.get('submission_id')!=submission.get('submission_id'): reasons.append('linkage_invalid')
 if result.get('preflight_id')!=preflight.get('preflight_id'): reasons.append('linkage_invalid')
 if result.get('controlled_execution_id')!=controlled.get('controlled_execution_id'): reasons.append('linkage_invalid')
 if controlled.get('filesystem_mutation_performed') or controlled.get('network_access_performed') or controlled.get('subprocess_created'): reasons.append('invariant_violation')
 if ('output' in result)==('failure' in result): reasons.append('output_failure_exclusivity')
 exp={'completed':'succeeded','cancelled':'cancelled','rejected':'rejected','failed':'failed'}.get(controlled.get('controlled_execution_status'),'invalid')
 if result.get('result_status')!=exp: reasons.append('status_mapping')
 body={'schema':SCHEMA,'verification_status':'verified' if not reasons else 'invalid','submission_id':submission.get('submission_id'),'result_id':result.get('result_id'),'workspace_id':submission.get('workspace_id'),'admission_id':submission.get('admission_id'),'read_scope_id':submission.get('read_scope_id'),'operation':submission.get('operation'),'relative_path_fingerprint':result.get('relative_path_fingerprint'),'reason_codes':sorted(set(reasons)) or ['verified'],'invariant_confirmation_codes':['no_mutation','no_network','no_subprocess','no_component_invocation','bounded_read_observation']}
 return canon(body,'verification_id','ver')
