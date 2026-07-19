from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_runtime_adapter_preparation_common import *
from core.engineering.engineering_runtime_adapter_preparation_request import validate_runtime_adapter_preparation_request
from core.engineering.engineering_runtime_adapter_preparation_policy import validate_runtime_adapter_preparation_policy
SCHEMA='zero.engineering.runtime_adapter_preparation_eligibility.v1';ID='preparation_eligibility_id';PREFIX='engineering-runtime-adapter-preparation-eligibility-'
FIELDS={'preparation_request_id','preparation_request_fingerprint','preparation_policy_id','preparation_policy_fingerprint','runtime_adapter_admission_id','runtime_adapter_admission_fingerprint','engineering_runtime_handoff_id','execution_session_id','requested_adapter_id','requested_adapter_version','eligibility_status','reason_codes'}
def evaluate_runtime_adapter_preparation_eligibility(request:Mapping[str,Any],policy:Mapping[str,Any],admission:Mapping[str,Any],handoff:Mapping[str,Any],session:Mapping[str,Any])->dict[str,Any]:
 reasons=[]
 if not validate_runtime_adapter_preparation_request(request).valid: reasons.append('invalid_request')
 if not validate_runtime_adapter_preparation_policy(policy).valid: reasons.append('invalid_policy')
 if admission.get('admission_status')!='admitted': reasons.append('admission_not_admitted')
 if request.get('runtime_adapter_admission_id')!=admission.get('admission_id') or request.get('runtime_adapter_admission_fingerprint')!=admission.get('fingerprint'): reasons.append('admission_linkage_mismatch')
 if request.get('engineering_runtime_handoff_id')!=handoff.get('engineering_runtime_handoff_id') or request.get('engineering_runtime_handoff_fingerprint')!=handoff.get('fingerprint'): reasons.append('handoff_linkage_mismatch')
 if request.get('execution_session_id')!=session.get('engineering_execution_session_id') or request.get('execution_session_fingerprint')!=session.get('fingerprint'): reasons.append('session_linkage_mismatch')
 if request.get('requested_adapter_id')!=admission.get('requested_adapter_id'): reasons.append('adapter_identity_mismatch')
 if request.get('requested_adapter_version')!=admission.get('requested_adapter_version'): reasons.append('adapter_version_mismatch')
 if not scope_bounded(request.get('requested_scope'),admission.get('admitted_scope')): reasons.append('scope_expansion')
 if contains_wildcard(request.get('requested_scope')): reasons.append('wildcard_scope')
 if not operation_valid(request.get('requested_operation')): reasons.append('invalid_operation')
 if not passive_mapping(request.get('input_bindings')): reasons.append('invalid_input_bindings')
 if not passive_mapping(request.get('expected_output_contract')): reasons.append('invalid_output_contract')
 if not resources_valid(request.get('resource_constraints')): reasons.append('unbounded_resources')
 if not timeout_valid(request.get('timeout_constraints')): reasons.append('invalid_timeout')
 if not environment_valid(request.get('environment_constraints')): reasons.append('invalid_environment_constraints')
 a=request.get('authority_constraints',{})
 if isinstance(a,Mapping):
  checks=(('non_transferable',True,'transferable_authority'),('non_reusable',True,'reusable_authority'),('scope_bound',True,'unbounded_authority'),('perpetual',False,'perpetual_authority'),('passive',True,'active_authority'),('consumed',False,'consumed_authority'),('closed',False,'closed_authority'),('unrestricted',False,'unrestricted_authority'),('restricted',True,'unrestricted_authority'))
  for k,val,code in checks:
   if a.get(k) is not val: reasons.append(code)
  if not scope_bounded(a.get('scope'),request.get('requested_scope')): reasons.append('unbounded_authority')
 if contains_prohibited(request): reasons.extend(['executable_payload','credential_like_payload'])
 reasons=normalize_reasons(reasons); status='invalid' if 'invalid_request' in reasons or 'invalid_policy' in reasons else ('ineligible' if reasons else 'eligible')
 return stable_artifact({'schema':SCHEMA,'preparation_request_id':request.get('preparation_request_id'),'preparation_request_fingerprint':request.get('fingerprint'),'preparation_policy_id':policy.get('preparation_policy_id'),'preparation_policy_fingerprint':policy.get('fingerprint'),'runtime_adapter_admission_id':request.get('runtime_adapter_admission_id'),'runtime_adapter_admission_fingerprint':request.get('runtime_adapter_admission_fingerprint'),'engineering_runtime_handoff_id':request.get('engineering_runtime_handoff_id'),'execution_session_id':request.get('execution_session_id'),'requested_adapter_id':request.get('requested_adapter_id'),'requested_adapter_version':request.get('requested_adapter_version'),'eligibility_status':status,'reason_codes':reasons},ID,PREFIX)
def validate_runtime_adapter_preparation_eligibility(v:Any)->ValidationResult: return validate_artifact(v,schema=SCHEMA,statuses={'eligible','ineligible','invalid'},id_key=ID,prefix=PREFIX,fields=FIELDS)
def inspect_runtime_adapter_preparation_eligibility(v:Any)->dict[str,Any]:
 r=validate_runtime_adapter_preparation_eligibility(v); return {'schema':SCHEMA,'valid':r.valid,'eligibility_status':v.get('eligibility_status') if isinstance(v,Mapping) else 'invalid','reason_codes':list(r.errors)}
