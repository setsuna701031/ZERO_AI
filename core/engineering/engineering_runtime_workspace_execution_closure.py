
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


SCHEMA='zero.engineering.runtime_workspace_execution_closure.v1'
def close_workspace_execution(result, verification, evidence):
 closed=verification.get('verification_status')=='verified' and result.get('result_status') in ('succeeded','rejected','cancelled','failed')
 body={'schema':SCHEMA,'closure_status':'closed' if closed else 'not_closed','workspace_id':result.get('workspace_id'),'operation':result.get('operation'),'relative_path_fingerprint':result.get('relative_path_fingerprint'),'result_status':result.get('result_status'),'verification_status':verification.get('verification_status'),'evidence_id':evidence.get('evidence_id'),'read_disposition':'read_performed' if result.get('result_status') in ('succeeded','failed') else 'no_read','mutation_invariant':'filesystem_mutation_performed_false','upstream_linkage_status':'linked' if result.get('submission_id') else 'invalid'}
 return canon(body,'closure_id','cls')
