from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_invocation_common import *
SCHEMA='zero.engineering.runtime_adapter_invocation_authorization.v1'
ID_KEY='invocation_authorization_id'
PREFIX='rtauthz-'
STATUS_KEY='authorization_status'
STATUSES={'not_authorized', 'invalid', 'authorized'}
FIELDS=set(['activation_handoff_id', 'activation_result_id', 'adapter_id', 'adapter_version', 'execution_session_id', 'invocation_descriptor_id', 'authority_reference', 'authority_constraints', 'reason_codes', 'adapter_loaded', 'adapter_code_executed', 'adapter_invoked', 'runtime_invoked', 'authority_consumed', 'mutation_performed', 'invocation_authorization_policy_id', 'invocation_authorization_policy_fingerprint', 'invocation_review_request_id', 'invocation_review_request_fingerprint', 'invocation_review_id', 'invocation_review_fingerprint', 'invocation_preparation_id', 'invocation_preparation_fingerprint', 'invocation_admission_id', 'invocation_admission_fingerprint', 'invocation_intake_id', 'invocation_intake_fingerprint', 'authorized_invocation_scope', 'operation', 'passive_only', 'invocation_authorized', 'invocation_committed', 'executor_invoked', 'scheduler_invoked'])
def _build(status, reasons, **kw):
 body={'schema':SCHEMA,**{k:v for k,v in kw.items() if k not in {STATUS_KEY,'reason_codes'}},STATUS_KEY:status,'reason_codes':normalize_reasons(reasons)}
 return stable_artifact(body,ID_KEY,PREFIX)
def _validate(v:Any):
 r=validate_artifact(v,schema=SCHEMA,id_key=ID_KEY,prefix=PREFIX,fields=FIELDS,status_key=STATUS_KEY,statuses=STATUSES)
 extra=[]
 if isinstance(v,Mapping): extra.extend(validate_common_invocation(v))
 return ValidationResult(r.valid and not extra, tuple(list(r.errors)+extra))
def validate_runtime_adapter_invocation_authorization(artifact:Any): return _validate(artifact)
def inspect_runtime_adapter_invocation_authorization(artifact:Any):
 r=_validate(artifact); return inspect_result(r.valid,r.errors)

POLICY_SCHEMA='zero.engineering.runtime_adapter_invocation_authorization_policy.v1'; POLICY_ID=ID_KEY.replace('_id','_policy_id'); POLICY_PREFIX=PREFIX+'p-'; POLICY_FIELDS=set('requires_valid_upstream requires_passive_only requires_no_real_execution invalid_input_fails_closed reason_codes'.split())
def build_default_runtime_adapter_invocation_authorization_policy(): return stable_artifact({'schema':POLICY_SCHEMA,'requires_valid_upstream':True,'requires_passive_only':True,'requires_no_real_execution':True,'invalid_input_fails_closed':True,'reason_codes':['default_policy']},POLICY_ID,POLICY_PREFIX)
def validate_runtime_adapter_invocation_authorization_policy(v): return validate_artifact(v,schema=POLICY_SCHEMA,id_key=POLICY_ID,prefix=POLICY_PREFIX,fields=POLICY_FIELDS)
def inspect_runtime_adapter_invocation_authorization_policy(v):
 r=validate_runtime_adapter_invocation_authorization_policy(v); return inspect_result(r.valid,r.errors)
def build_runtime_adapter_invocation_authorization(upstream, policy=None):
 u=upstream if isinstance(upstream,Mapping) else {}; p=policy or build_default_runtime_adapter_invocation_authorization_policy(); ok=validate_runtime_adapter_invocation_authorization_policy(p).valid and isinstance(upstream,Mapping) and (u.get('admission_status')=='admitted' or u.get('review_status')=='approved')
 st='authorized' if ok else ('invalid' if not isinstance(upstream,Mapping) else 'not_authorized')
 return _build(st,[st], **{'activation_handoff_id':u.get('activation_handoff_id'),'activation_handoff_fingerprint':u.get('activation_handoff_fingerprint'),'activation_result_id':u.get('activation_result_id'),'adapter_id':u.get('adapter_id'),'adapter_version':u.get('adapter_version'),'execution_session_id':u.get('execution_session_id'),'invocation_descriptor_id':u.get('invocation_descriptor_id'),'authority_reference':u.get('authority_reference'),'authority_constraints':u.get('authority_constraints'),'invocation_intake_id':u.get('invocation_intake_id'),'invocation_intake_fingerprint':u.get('invocation_intake_fingerprint'),'invocation_admission_id':u.get('invocation_admission_id'),'invocation_admission_fingerprint':u.get('fingerprint'),'invocation_preparation_policy_id':p.get(POLICY_ID),'invocation_preparation_policy_fingerprint':p.get('fingerprint'),'invocation_authorization_policy_id':p.get(POLICY_ID),'invocation_authorization_policy_fingerprint':p.get('fingerprint'),'invocation_review_request_id':u.get('invocation_review_request_id'),'invocation_review_request_fingerprint':u.get('invocation_review_request_fingerprint'),'invocation_review_id':u.get('invocation_review_id'),'invocation_review_fingerprint':u.get('fingerprint'),'invocation_preparation_id':u.get('invocation_preparation_id'),'invocation_preparation_fingerprint':u.get('fingerprint'),'invocation_intake_request_id':u.get('invocation_intake_request_id'),'invocation_intake_request_fingerprint':u.get('invocation_intake_request_fingerprint'),'admitted_scope':u.get('admitted_scope'),'prepared_invocation_scope':u.get('admitted_scope',u.get('prepared_invocation_scope')),'authorized_invocation_scope':u.get('prepared_invocation_scope',u.get('review_scope')),'operation':u.get('operation'),'input_bindings':u.get('input_bindings'),'expected_output_contract':u.get('expected_output_contract'),'invocation_configuration':{'passive_only':True,'operation':u.get('operation')},'resource_constraints':u.get('resource_constraints'),'timeout_constraints':u.get('timeout_constraints'),'environment_constraints':u.get('environment_constraints'),'passive_only':True,'invocation_authorized':st=='authorized','invocation_committed':False,'adapter_loaded':False,'adapter_code_executed':False,'adapter_invoked':False,'runtime_invoked':False,'executor_invoked':False,'scheduler_invoked':False,'authority_consumed':False,'mutation_performed':False})
