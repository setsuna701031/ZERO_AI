
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

SCHEMA='zero.engineering.runtime_workspace_read_scope.v1'
def create_read_scope(allowed_relative_path_prefixes=('',), allowed_operations=OPERATIONS, max_read_bytes=65536, max_hash_bytes=1048576, max_directory_entries=100, max_relative_path_length=512, max_path_segments=32, allow_symlinks=False, allow_hidden_entries=True, allow_binary_hashing=True, allow_text_read=True):
 body={'schema':SCHEMA,'allowed_relative_path_prefixes':sorted(allowed_relative_path_prefixes),'allowed_operations':sorted(allowed_operations),'max_read_bytes':max_read_bytes,'max_hash_bytes':max_hash_bytes,'max_directory_entries':max_directory_entries,'max_relative_path_length':max_relative_path_length,'max_path_segments':max_path_segments,'allow_symlinks':allow_symlinks,'allow_hidden_entries':allow_hidden_entries,'allow_binary_hashing':allow_binary_hashing,'allow_text_read':allow_text_read}
 return canon(body,'scope_id','scp')
def validate_scope_request(scope, operation, relative_path, params=None):
 errs=[]; params=params or {}
 if operation not in scope.get('allowed_operations',[]): errs.append('operation_not_allowed')
 if len(relative_path)>scope.get('max_relative_path_length',0): errs.append('path_invalid')
 parts=[x for x in relative_path.split('/') if x]
 if len(parts)>scope.get('max_path_segments',0): errs.append('path_invalid')
 if not any(relative_path==p or p=='' or relative_path.startswith(p.rstrip('/')+'/') for p in scope.get('allowed_relative_path_prefixes',[])): errs.append('path_outside_workspace')
 for k,m in [('max_read_bytes','max_read_bytes'),('max_hash_bytes','max_hash_bytes'),('max_directory_entries','max_directory_entries')]:
  if k in params and params[k]>scope[m]: errs.append('scope_expansion')
 return (not errs, sorted(set(errs)))
