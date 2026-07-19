
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

SCHEMA='zero.engineering.runtime_workspace_root_admission.v1'
class WorkspaceAdmission(dict):
 def __init__(self,*a,root_path:Path|None=None,**k): super().__init__(*a,**k); self.root_path=root_path
def admit_workspace_root(root:Any, workspace_id='workspace', allow_home_for_tests=False)->WorkspaceAdmission:
 reasons=[]; p=Path(root) if root is not None else None; resolved=None; admitted=False; kind='missing'
 try:
  if p is None: reasons.append('workspace_missing')
  else:
   resolved=p.resolve(strict=True); kind='directory' if resolved.is_dir() else ('file' if resolved.is_file() else 'other')
   home=Path.home().resolve()
   if not resolved.is_dir(): reasons.append('workspace_not_directory' if resolved.exists() else 'workspace_missing')
   elif resolved.parent==resolved: reasons.append('drive_or_filesystem_root_disallowed')
   elif resolved==home and not allow_home_for_tests: reasons.append('home_root_disallowed')
   else: admitted=True; reasons.append('admitted')
 except Exception: reasons.append('workspace_missing')
 fp=hashlib.sha256(str(resolved or p or '').encode()).hexdigest()
 body=WorkspaceAdmission({'schema':SCHEMA,'workspace_id':workspace_id,'workspace_root_fingerprint':fp,'root_kind':kind,'admitted':admitted,'read_only':True,'reason_codes':sorted(set(reasons))}, root_path=resolved if admitted else None)
 body.update(canon(dict(body),'admission_id','adm'))
 return body
