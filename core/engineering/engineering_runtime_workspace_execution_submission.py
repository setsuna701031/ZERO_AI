
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


from core.engineering.engineering_runtime_workspace_read_scope import validate_scope_request
SCHEMA='zero.engineering.runtime_workspace_execution_submission.v1'
def build_workspace_execution_submission(executor_handoff, integration_closure, admission, read_scope, operation, relative_path='', operation_parameters=None, execution_session_id='workspace-session', adapter_id=ADAPTER_ID, adapter_version=ADAPTER_VERSION, expected_output_contract='zero.engineering.runtime_workspace_observation_output.v1', authority_constraints=None, resource_policy=None, timeout_policy=None, cancellation_state=None):
 params=operation_parameters or {}; reasons=[]
 if adapter_id!=ADAPTER_ID or str(adapter_version)!=ADAPTER_VERSION: reasons.append('adapter_substitution')
 ok,errs=validate_scope_request(read_scope,operation,str(relative_path or ''),params); reasons+=errs
 if not admission.get('admitted'): reasons.append('workspace_not_admitted')
 if authority_constraints and any(authority_constraints.values()): reasons.append('authority_expansion')
 body={'schema':SCHEMA,'executor_handoff_id':executor_handoff.get('executor_handoff_id') or executor_handoff.get('handoff_id'),'upstream_execution_integration_closure_id':integration_closure.get('closure_id') or integration_closure.get('integration_closure_id'),'workspace_id':admission.get('workspace_id'),'admission_id':admission.get('admission_id'),'read_scope_id':read_scope.get('scope_id'),'adapter_id':adapter_id,'adapter_version':str(adapter_version),'execution_session_id':execution_session_id,'operation':operation,'relative_path':str(relative_path or ''),'operation_parameters':params,'expected_output_contract':expected_output_contract,'authority_constraints':authority_constraints or {'network':False,'subprocess':False,'external_authority':False},'resource_policy':resource_policy or {},'timeout_policy':timeout_policy or {},'cancellation_state':cancellation_state or {'cancelled':False},'accepted':not reasons,'reason_codes':sorted(set(reasons)) or ['accepted']}
 return canon(body,'submission_id','sub')
