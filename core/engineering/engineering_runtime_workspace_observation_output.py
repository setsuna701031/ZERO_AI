
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


SCHEMA='zero.engineering.runtime_workspace_observation_output.v1'
def validate_observation_output(operation:str, output:Mapping[str,Any]):
 required={'workspace_exists':('exists','path_kind'),'path_exists':('relative_path','exists','path_kind'),'path_kind':('relative_path','path_kind'),'list_directory':('relative_path','entry_count','entries'),'read_text':('relative_path','encoding','size_bytes','content','content_sha256'),'file_sha256':('relative_path','size_bytes','sha256'),'file_metadata':('relative_path','path_kind','size_bytes','readable','symlink')}.get(operation,())
 errs=[k for k in required if k not in output]
 s=json.dumps(output,sort_keys=True,ensure_ascii=False)
 if len(s)>200000: errs.append('output_too_large')
 if 'absolute_path' in s: errs.append('absolute_path')
 return (not errs,errs)
def build_observation_output(operation:str, payload:Mapping[str,Any]):
 ok,errs=validate_observation_output(operation,payload)
 body={'schema':SCHEMA,'operation':operation,'valid':ok,'reason_codes':errs or ['valid'],'payload':dict(payload)}
 return canon(body,'output_id','out')
