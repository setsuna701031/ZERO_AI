
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


from core.engineering.engineering_runtime_workspace_root_admission import WorkspaceAdmission
SCHEMA='zero.engineering.runtime_workspace_path_resolution.v1'
def _invalid_path(s:str):
 if '\x00' in s or s.startswith(('//','\\\\')) or os.path.isabs(s): return True
 if PureWindowsPath(s).drive or ':' in s: return True
 if '\\' in s: s=s.replace('\\','/')
 if '//' in s or s.startswith('./') or '/./' in s: return True
 parts=s.split('/') if s else []
 return any(part in ('..','') for part in parts)
def path_kind_for(p:Path)->str:
 try:
  if not p.exists() and not p.is_symlink(): return 'missing'
  if p.is_symlink(): return 'symlink'
  if p.is_file(): return 'file'
  if p.is_dir(): return 'directory'
  return 'other'
 except Exception: return 'other'
def resolve_workspace_path(admission:Mapping[str,Any], relative_path:str='', allow_root:bool=True, allow_symlinks:bool=False):
 reasons=[]; rp=str(relative_path or '')
 if rp=='' and not allow_root: reasons.append('path_invalid')
 if _invalid_path(rp): reasons.append('path_invalid')
 root=getattr(admission,'root_path',None)
 if not admission.get('admitted') or root is None: reasons.append('workspace_not_admitted')
 resolved=None; kind='missing'; symlink=False
 if not reasons:
  try:
   root=Path(root).resolve(strict=True); cand=(root / rp).resolve(strict=False)
   if not (cand==root or root in cand.parents): reasons.append('path_outside_workspace')
   # detect symlink in existing path components without following outside silently
   cur=root
   for part in [x for x in rp.split('/') if x]:
    cur=cur/part
    if cur.is_symlink(): symlink=True; break
   if symlink and not allow_symlinks: reasons.append('symlink_disallowed')
   resolved=cand if not reasons else None; kind=path_kind_for(cand)
  except Exception: reasons.append('path_invalid')
 body={'schema':SCHEMA,'workspace_id':admission.get('workspace_id'),'admission_id':admission.get('admission_id'),'relative_path':rp,'relative_path_fingerprint':hashlib.sha256(rp.encode()).hexdigest(),'path_kind':kind,'resolved':not reasons,'symlink_detected':symlink,'inside_workspace':'path_outside_workspace' not in reasons,'reason_codes':sorted(set(reasons)) or ['resolved']}
 art=canon(body,'path_resolution_id','prs')
 return art,resolved
