from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_activation_common import *
from core.engineering.engineering_runtime_adapter_activation_admission import validate_runtime_adapter_activation_admission
SCHEMA='zero.engineering.runtime_adapter_activation_preparation.v1'
ID_KEY='activation_preparation_id'
PREFIX='rtap-'
STATUS_KEY='preparation_status'
STATUSES={'prepared', 'invalid', 'not_prepared'}
BASE_FIELDS={'admitted_scope', 'token_id', 'token_authorization_id', 'execution_session_id', 'invocation_descriptor_id', 'environment_constraints', 'prepared_activation_scope', 'activation_admission_request_id', 'activation_admission_fingerprint', 'adapter_version', 'authority_constraints', 'token_fingerprint', 'activation_admission_id', 'authority_reference', 'token_verification_id', 'activation_configuration', 'resource_constraints', 'activation_preparation_policy_fingerprint', 'token_handoff_id', 'activation_admission_request_fingerprint', 'activation_preparation_policy_id', 'token_handoff_fingerprint', 'adapter_id', 'timeout_constraints'}
COMMON_BOOL={'adapter_loaded':False,'adapter_invoked':False,'runtime_invoked':False,'authority_consumed':False}
def _ok(v): return isinstance(v,Mapping) and not contains_prohibited(v)
def _build(status, reasons, **kw):
 body={'schema':SCHEMA,**{k:v for k,v in kw.items() if k!=STATUS_KEY},STATUS_KEY:status,'reason_codes':normalize_reasons(reasons)}
 return stable_artifact(body,ID_KEY,PREFIX)
def _validate(v):
 fields=set(BASE_FIELDS)|{STATUS_KEY,'reason_codes'}
 fields|={k for k in v if isinstance(k,str) and k not in {'schema',ID_KEY,'fingerprint'}} if isinstance(v,Mapping) else set()
 r=validate_artifact(v,schema=SCHEMA,id_key=ID_KEY,prefix=PREFIX,fields=fields,status_key=STATUS_KEY,statuses=STATUSES if STATUS_KEY!='eligible_for_invocation_governance' else {True,False})
 extra=[]
 if isinstance(v,Mapping) and not passive_false(v): extra.append('non_execution_invariant_failed')
 return ValidationResult(r.valid and not extra, tuple(list(r.errors)+extra))
def validate_runtime_adapter_activation_preparation(artifact:Any): return _validate(artifact)
def inspect_runtime_adapter_activation_preparation(artifact:Any):
 r=_validate(artifact); return inspect_result(r.valid,r.errors)
POL_SCHEMA='zero.engineering.runtime_adapter_activation_preparation_policy.v1'
def build_default_runtime_adapter_activation_preparation_policy(): return stable_artifact({'schema':POL_SCHEMA,'requires_admitted':True,'passive_only':True,'bounded_resources':True,'finite_timeout':True},'activation_preparation_policy_id','rtapp-')
def validate_runtime_adapter_activation_preparation_policy(p): return validate_artifact(p,schema=POL_SCHEMA,id_key='activation_preparation_policy_id',prefix='rtapp-',fields={'requires_admitted','passive_only','bounded_resources','finite_timeout'})
def inspect_runtime_adapter_activation_preparation_policy(p):
 r=validate_runtime_adapter_activation_preparation_policy(p); return inspect_result(r.valid,r.errors)
def build_runtime_adapter_activation_preparation(admission, policy, activation_configuration=None, resource_constraints=None, timeout_constraints=None, environment_constraints=None):
 a=admission if isinstance(admission,Mapping) else {}; cfg=activation_configuration or {'passive_only':True}; res=resource_constraints or {'max_units':1}; tout=timeout_constraints or {'seconds':1}; env=environment_constraints or {'passive':True}
 ok=validate_runtime_adapter_activation_admission(a).valid and a.get('admission_status')=='admitted' and validate_runtime_adapter_activation_preparation_policy(policy).valid and activation_configuration_valid(cfg) and resource_constraints_valid(res) and timeout_constraints_valid(tout) and isinstance(env,Mapping) and env.get('passive') is True and not contains_prohibited(env)
 return _build('prepared' if ok else 'not_prepared', ['prepared'] if ok else ['preparation_prerequisite_failed'], **{k:a.get(k) for k in ['activation_admission_request_id','activation_admission_request_fingerprint','token_handoff_id','token_handoff_fingerprint','token_id','token_fingerprint','token_verification_id','token_authorization_id','adapter_id','adapter_version','execution_session_id','invocation_descriptor_id','authority_reference','authority_constraints']}, activation_admission_id=a.get('activation_admission_id'), activation_admission_fingerprint=a.get('fingerprint'), activation_preparation_policy_id=policy.get('activation_preparation_policy_id') if isinstance(policy,Mapping) else None, activation_preparation_policy_fingerprint=policy.get('fingerprint') if isinstance(policy,Mapping) else None, admitted_scope=a.get('activation_scope'), prepared_activation_scope=a.get('activation_scope'), activation_configuration=cfg, resource_constraints=res, timeout_constraints=tout, environment_constraints=env, passive_only=True, activation_committed=False, token_consumed=False, adapter_loaded=False, adapter_activated=False, adapter_invoked=False, runtime_invoked=False, authority_consumed=False, mutation_performed=False)
