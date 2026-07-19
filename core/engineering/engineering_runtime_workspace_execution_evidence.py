
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


SCHEMA='zero.engineering.runtime_workspace_execution_evidence.v1'
def build_workspace_execution_evidence(submission, preflight, controlled, result, verification):
 payload=result.get('output',{}).get('payload',{}) if result.get('output') else {}
 body={'schema':SCHEMA,'stage_codes':['submission','preflight','controlled_execution','result','verification'],'decision_codes':preflight.get('reason_codes',[])+verification.get('reason_codes',[]),'submission_id':submission.get('submission_id'),'preflight_id':preflight.get('preflight_id'),'controlled_execution_id':controlled.get('controlled_execution_id'),'result_id':result.get('result_id'),'verification_id':verification.get('verification_id'),'workspace_id':submission.get('workspace_id'),'admission_id':submission.get('admission_id'),'read_scope_id':submission.get('read_scope_id'),'operation':submission.get('operation'),'status':result.get('result_status'),'relative_path_fingerprint':result.get('relative_path_fingerprint'),'byte_counts':{'size_bytes':payload.get('size_bytes')},'entry_counts':{'entry_count':payload.get('entry_count')},'invariant_confirmation_codes':verification.get('invariant_confirmation_codes',[])}
 return canon(body,'evidence_id','evd')
