
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


from core.engineering.engineering_runtime_workspace_path_resolution import path_kind_for
class ReadOnlyWorkspaceAdapter:
 adapter_id=ADAPTER_ID; adapter_version=ADAPTER_VERSION
 def perform(self, operation:str, root_path:Path, resolved_path:Path, relative_path:str, scope:Mapping[str,Any], params:Mapping[str,Any]|None=None):
  params=params or {}; max_entries=int(params.get('max_directory_entries',scope.get('max_directory_entries',100)))
  if operation=='workspace_exists': return {'exists':root_path.exists() and root_path.is_dir(),'path_kind':path_kind_for(root_path)}
  kind=path_kind_for(resolved_path)
  if operation=='path_exists': return {'relative_path':relative_path,'exists':kind!='missing','path_kind':kind}
  if operation=='path_kind': return {'relative_path':relative_path,'path_kind':kind}
  if resolved_path.is_symlink() and not scope.get('allow_symlinks',False): raise ValueError('symlink_disallowed')
  if operation=='list_directory':
   if not resolved_path.is_dir(): raise ValueError('path_not_directory')
   entries=[]
   for child in resolved_path.iterdir():
    name=child.name
    if not scope.get('allow_hidden_entries',True) and name.startswith('.'): continue
    entries.append({'name':name,'path_kind':path_kind_for(child),'symlink':child.is_symlink()})
    if len(entries)>max_entries: raise ValueError('directory_entry_limit_exceeded')
   entries=sorted(entries,key=lambda e:e['name'])
   return {'relative_path':relative_path,'entry_count':len(entries),'entries':entries}
  if operation=='read_text':
   if not scope.get('allow_text_read',True): raise ValueError('operation_not_allowed')
   if not resolved_path.is_file(): raise ValueError('path_not_file')
   size=resolved_path.stat().st_size; limit=int(params.get('max_read_bytes',scope.get('max_read_bytes',65536)))
   if size>limit: raise ValueError('file_too_large')
   data=resolved_path.read_bytes()
   if len(data)>limit: raise ValueError('file_too_large')
   try: text=data.decode('utf-8')
   except UnicodeDecodeError: raise ValueError('invalid_utf8')
   return {'relative_path':relative_path,'encoding':'utf-8','size_bytes':len(data),'content':text,'content_sha256':hashlib.sha256(data).hexdigest()}
  if operation=='file_sha256':
   if not resolved_path.is_file(): raise ValueError('path_not_file')
   size=resolved_path.stat().st_size; limit=int(params.get('max_hash_bytes',scope.get('max_hash_bytes',1048576)))
   if size>limit: raise ValueError('file_too_large')
   h=hashlib.sha256()
   with resolved_path.open('rb') as fh:
    while True:
     chunk=fh.read(65536)
     if not chunk: break
     h.update(chunk)
   return {'relative_path':relative_path,'size_bytes':size,'sha256':h.hexdigest()}
  if operation=='file_metadata':
   size=resolved_path.stat().st_size if resolved_path.exists() and resolved_path.is_file() else None
   return {'relative_path':relative_path,'path_kind':kind,'size_bytes':size,'readable':resolved_path.exists(),'symlink':resolved_path.is_symlink()}
  raise ValueError('operation_not_allowed')
