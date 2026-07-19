from __future__ import annotations
from typing import Any
from core.engineering.engineering_mutation_preparation_common import *
def build_mutation_preparation_policy(payload:dict[str,Any])->dict[str,Any]:
 rs=[]
 for n in ('maximum_prepared_operations','maximum_prepared_files','maximum_prepared_content_bytes','maximum_prepared_diff_entries'): rs+=bounded_int(payload.get(n,0),n,1)
 for k in ('allow_symlink','allow_binary','allow_git','allow_shell','allow_external_tools'):
  if payload.get(k) is not False: rs.append(k+'_not_allowed')
 if payload.get('token_use_limit',1)!=1: rs.append('token_use_limit_not_one')
 body={**payload,'allowed_prepared_operation_classes':seq(payload.get('allowed_prepared_operation_classes')) or list(OP_TYPES),'allowed_path_prefixes':seq(payload.get('allowed_path_prefixes')),'required_precondition_modes':seq(payload.get('required_precondition_modes')),'require_exact_before_fingerprint':bool(payload.get('require_exact_before_fingerprint',True)),'require_exact_workspace_identity':bool(payload.get('require_exact_workspace_identity',True)),'require_operator_approval_verification':bool(payload.get('require_operator_approval_verification',True)),'require_one_time_token':bool(payload.get('require_one_time_token',True)),'token_use_limit':1,'allow_partial_preparation':bool(payload.get('allow_partial_preparation',True)),'allow_create':bool(payload.get('allow_create',True)),'allow_replace':bool(payload.get('allow_replace',True)),'allow_delete':bool(payload.get('allow_delete',True)),'allow_create_directory':bool(payload.get('allow_create_directory',True)),'allow_rename':bool(payload.get('allow_rename',True)),'allow_symlink':False,'allow_binary':False,'allow_git':False,'allow_shell':False,'allow_external_tools':False,'mutation_authorized':False,'status':'active' if not rs else 'invalid','reason_codes':reasons(rs)}
 return artifact('mpp',SCHEMAS['mutation_preparation_policy'],body,'preparation_policy_id')
