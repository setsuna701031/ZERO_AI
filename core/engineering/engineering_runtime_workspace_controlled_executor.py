
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


from core.engineering.engineering_runtime_workspace_execution_failure import build_workspace_execution_failure
from core.engineering.engineering_runtime_workspace_observation_output import build_observation_output
from core.engineering.engineering_runtime_workspace_path_resolution import resolve_workspace_path
SCHEMA='zero.engineering.runtime_workspace_controlled_execution.v1'
FALSE_FLAGS={'filesystem_mutation_performed':False,'network_access_performed':False,'subprocess_created':False,'thread_created':False,'runtime_kernel_invoked':False,'scheduler_invoked':False,'planner_invoked':False,'worker_invoked':False,'mission_invoked':False,'external_effects_performed':False}
def execute_workspace_adapter(submission, preflight, registry, admission, read_scope):
 base={'schema':SCHEMA,'submission_id':submission.get('submission_id'),'preflight_id':preflight.get('preflight_id'),'operation':submission.get('operation'),'relative_path_fingerprint':hashlib.sha256(str(submission.get('relative_path','')).encode()).hexdigest(),'invocation_started':False,'adapter_invoked':False,'invocation_completed':False,'filesystem_read_performed':False,**FALSE_FLAGS}
 if preflight.get('preflight_status')=='cancelled': return canon({**base,'controlled_execution_status':'cancelled','failure':build_workspace_execution_failure('cancellation_requested','preflight')},'controlled_execution_id','cex')
 if not preflight.get('adapter_invocation_allowed'): return canon({**base,'controlled_execution_status':'rejected','failure':build_workspace_execution_failure(preflight.get('reason_codes',['linkage_invalid'])[0],'preflight')},'controlled_execution_id','cex')
 adapter=registry.lookup(submission['adapter_id'],submission['adapter_version']); art,resolved=resolve_workspace_path(admission,submission.get('relative_path',''),allow_root=True,allow_symlinks=read_scope.get('allow_symlinks',False))
 try:
  payload=adapter.perform(submission['operation'], getattr(admission,'root_path'), resolved, submission.get('relative_path',''), read_scope, submission.get('operation_parameters') or {})
  out=build_observation_output(submission['operation'], payload)
  return canon({**base,'invocation_started':True,'adapter_invoked':True,'invocation_completed':True,'filesystem_read_performed':True,'controlled_execution_status':'completed','output':out},'controlled_execution_id','cex')
 except Exception as e:
  code=str(e) if str(e) in FAILURE_CODES else {'PermissionError':'permission_denied'}.get(type(e).__name__,'read_failed')
  return canon({**base,'invocation_started':True,'adapter_invoked':True,'invocation_completed':True,'filesystem_read_performed':True,'controlled_execution_status':'failed','failure':build_workspace_execution_failure(code,'filesystem_read')},'controlled_execution_id','cex')
