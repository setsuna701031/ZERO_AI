from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_activation_common import *
SCHEMA='zero.engineering.runtime_adapter_controlled_activation.v1'
ID_KEY='controlled_activation_id'
PREFIX='rtca-'
STATUS_KEY='activation_status'
STATUSES={'activated', 'not_activated', 'invalid'}
BASE_FIELDS={'token_id', 'token_authorization_id', 'activation_preparation_id', 'activation_authorization_id', 'execution_session_id', 'invocation_descriptor_id', 'activated_scope', 'activation_preparation_fingerprint', 'activation_admission_fingerprint', 'adapter_version', 'authority_constraints', 'token_fingerprint', 'activation_admission_id', 'authority_reference', 'token_verification_id', 'activation_configuration', 'token_handoff_id', 'token_handoff_fingerprint', 'adapter_id'}
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
def validate_runtime_adapter_controlled_activation(artifact:Any): return _validate(artifact)
def inspect_runtime_adapter_controlled_activation(artifact:Any):
 r=_validate(artifact); return inspect_result(r.valid,r.errors)
from core.engineering.engineering_runtime_adapter_activation_admission import validate_runtime_adapter_activation_admission
from core.engineering.engineering_runtime_adapter_activation_preparation import validate_runtime_adapter_activation_preparation
def build_runtime_adapter_controlled_activation(preparation, admission):
 p=preparation if isinstance(preparation,Mapping) else {}; a=admission if isinstance(admission,Mapping) else {}
 ok=validate_runtime_adapter_activation_preparation(p).valid and p.get('preparation_status')=='prepared' and validate_runtime_adapter_activation_admission(a).valid and a.get('admission_status')=='admitted' and exact(p,a,['token_id','adapter_id','adapter_version','execution_session_id','invocation_descriptor_id']) and scope_bounded(p.get('prepared_activation_scope'),a.get('activation_scope'))
 return _build('activated' if ok else 'not_activated', ['activated'] if ok else ['activation_prerequisite_failed'], **{k:p.get(k) for k in BASE_FIELDS if k!='activated_scope'}, activated_scope=p.get('prepared_activation_scope'), governance_transition_committed=ok, activation_authorized=ok, token_consumption_required=ok, adapter_loaded=False, adapter_code_executed=False, adapter_invoked=False, runtime_invoked=False, executor_invoked=False, scheduler_invoked=False, authority_consumed=False, repository_mutation_performed=False)
