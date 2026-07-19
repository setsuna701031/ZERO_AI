from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_activation_common import *
SCHEMA='zero.engineering.runtime_adapter_activation_result.v1'
ID_KEY='activation_result_id'
PREFIX='rtar-'
STATUS_KEY='result_status'
STATUSES={'activated', 'not_activated', 'invalid'}
BASE_FIELDS={'controlled_activation_id', 'adapter_id', 'token_id', 'token_consumption_id', 'activation_preparation_id', 'controlled_activation_fingerprint', 'adapter_version', 'execution_session_id', 'token_consumption_fingerprint', 'invocation_descriptor_id', 'activated_scope', 'activation_admission_id'}
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
def validate_runtime_adapter_activation_result(artifact:Any): return _validate(artifact)
def inspect_runtime_adapter_activation_result(artifact:Any):
 r=_validate(artifact); return inspect_result(r.valid,r.errors)
from core.engineering.engineering_runtime_adapter_controlled_activation import validate_runtime_adapter_controlled_activation
from core.engineering.engineering_runtime_adapter_activation_token_consumption import validate_runtime_adapter_activation_token_consumption
def build_runtime_adapter_activation_result(controlled_activation, token_consumption):
 c=controlled_activation if isinstance(controlled_activation,Mapping) else {}; t=token_consumption if isinstance(token_consumption,Mapping) else {}
 ok=validate_runtime_adapter_controlled_activation(c).valid and c.get('activation_status')=='activated' and validate_runtime_adapter_activation_token_consumption(t).valid and t.get('consumption_status')=='consumed' and c.get('controlled_activation_id')==t.get('controlled_activation_id')
 return _build('activated' if ok else 'not_activated', ['activated'] if ok else ['activation_result_prerequisite_failed'], **{k:c.get(k) for k in ['activation_preparation_id','activation_admission_id','token_id','adapter_id','adapter_version','execution_session_id','invocation_descriptor_id']}, controlled_activation_id=c.get('controlled_activation_id'), controlled_activation_fingerprint=c.get('fingerprint'), token_consumption_id=t.get('token_consumption_id'), token_consumption_fingerprint=t.get('fingerprint'), activated_scope=c.get('activated_scope'), governance_transition_committed=ok, token_consumed=ok, adapter_activation_state='governance_activated' if ok else 'not_activated', adapter_loaded=False, adapter_code_executed=False, adapter_invoked=False, runtime_invoked=False, executor_invoked=False, scheduler_invoked=False, authority_consumed=False, mutation_performed=False)
