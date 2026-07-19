
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

SCHEMA='zero.engineering.runtime_workspace_adapter_descriptor.v1'
def build_workspace_adapter_descriptor(adapter:Any|None=None)->dict[str,Any]:
 body={'schema':SCHEMA,'adapter_id':ADAPTER_ID,'adapter_version':ADAPTER_VERSION,'execution_mode':EXECUTION_MODE,'supported_operations':list(OPERATIONS),'deterministic_metadata':True,'read_only':True,'filesystem_mutation_allowed':False,'network_allowed':False,'subprocess_allowed':False,'external_authority_allowed':False,'supports_cancellation':'pre_start_only','recursive_traversal_allowed':False,'absolute_path_input_allowed':False}
 return canon(body,'descriptor_id','wad')
def validate_workspace_adapter_descriptor(d:Mapping[str,Any])->tuple[bool,list[str]]:
 errs=[]
 for k,v in {'schema':SCHEMA,'adapter_id':ADAPTER_ID,'adapter_version':ADAPTER_VERSION,'execution_mode':EXECUTION_MODE,'read_only':True,'filesystem_mutation_allowed':False,'network_allowed':False,'subprocess_allowed':False,'external_authority_allowed':False,'supports_cancellation':'pre_start_only','recursive_traversal_allowed':False,'absolute_path_input_allowed':False}.items():
  if d.get(k)!=v: errs.append(k)
 if tuple(d.get('supported_operations',()))!=OPERATIONS: errs.append('supported_operations')
 return (not errs,errs)
