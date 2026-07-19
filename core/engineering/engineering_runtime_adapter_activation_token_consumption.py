from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_activation_common import *
SCHEMA='zero.engineering.runtime_adapter_activation_token_consumption.v1'
ID_KEY='token_consumption_id'
PREFIX='rtatc-'
STATUS_KEY='consumption_status'
STATUSES={'not_consumed', 'consumed', 'invalid'}
BASE_FIELDS={'token_verification_id', 'controlled_activation_id', 'invocation_descriptor_id', 'consumed_scope', 'adapter_id', 'token_id', 'activation_preparation_id', 'controlled_activation_fingerprint', 'activation_authorization_id', 'adapter_version', 'execution_session_id', 'token_fingerprint', 'token_handoff_id', 'activation_admission_id', 'token_issuance_id'}
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
def validate_runtime_adapter_activation_token_consumption(artifact:Any): return _validate(artifact)
def inspect_runtime_adapter_activation_token_consumption(artifact:Any):
 r=_validate(artifact); return inspect_result(r.valid,r.errors)
from core.engineering.engineering_runtime_adapter_controlled_activation import validate_runtime_adapter_controlled_activation
def build_runtime_adapter_activation_token_consumption(controlled_activation):
 c=controlled_activation if isinstance(controlled_activation,Mapping) else {}; ok=validate_runtime_adapter_controlled_activation(c).valid and c.get('activation_status')=='activated'
 return _build('consumed' if ok else 'not_consumed', ['consumed'] if ok else ['controlled_activation_not_activated'], **{k:c.get(k) for k in ['token_id','token_fingerprint','token_verification_id','token_handoff_id','activation_preparation_id','activation_admission_id','activation_authorization_id','adapter_id','adapter_version','execution_session_id','invocation_descriptor_id']}, token_issuance_id=c.get('token_issuance_id'), controlled_activation_id=c.get('controlled_activation_id'), controlled_activation_fingerprint=c.get('fingerprint'), consumed_scope=c.get('activated_scope'), max_uses=1, previous_uses=0, current_uses=1 if ok else 0, token_state_before='issued_unconsumed', token_state_after='consumed' if ok else 'issued_unconsumed', governance_consumption_only=ok, secret_material_consumed=False, external_credential_consumed=False, adapter_loaded=False, adapter_invoked=False, runtime_invoked=False, authority_consumed=False, mutation_performed=False)
