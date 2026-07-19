
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

from core.engineering.engineering_runtime_workspace_adapter_protocol import build_workspace_adapter_descriptor, validate_workspace_adapter_descriptor
REGISTRY_SCHEMA='zero.engineering.runtime_workspace_adapter_registry_snapshot.v1'
class WorkspaceAdapterRegistry:
 def __init__(self, adapters=()):
  self._adapters={}; self._descriptors={}
  for a in adapters: self.register(a)
 def register(self, adapter:Any):
  d=build_workspace_adapter_descriptor(adapter); ok,errs=validate_workspace_adapter_descriptor(d)
  if not ok: raise ValueError('invalid_descriptor')
  key=(d['adapter_id'],d['adapter_version'])
  if key in self._adapters: raise ValueError('duplicate_adapter_registration')
  self._adapters[key]=adapter; self._descriptors[key]=d
 def lookup(self, adapter_id:str, adapter_version:str): return self._adapters.get((adapter_id,str(adapter_version)))
 def descriptor(self, adapter_id:str, adapter_version:str): return self._descriptors.get((adapter_id,str(adapter_version)))
 def snapshot(self):
  body={'schema':REGISTRY_SCHEMA,'descriptors':[self._descriptors[k] for k in sorted(self._descriptors)]}
  body['registry_fingerprint']=canonical_fingerprint(body); body['fingerprint']=body['registry_fingerprint']; body['registry_id']='war-'+body['fingerprint'][:24]; return body
def default_workspace_adapter_registry():
 from core.engineering.engineering_runtime_read_only_workspace_adapter import ReadOnlyWorkspaceAdapter
 return WorkspaceAdapterRegistry((ReadOnlyWorkspaceAdapter(),))
