from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_activation_common import *
SCHEMA='zero.engineering.runtime_adapter_activation_handoff.v1'
ID_KEY='activation_handoff_id'
PREFIX='rtah-'
STATUS_KEY='eligible_for_invocation_governance'
STATUSES={False, True}
BASE_FIELDS={'activation_verification_fingerprint', 'controlled_activation_id', 'adapter_id', 'activation_verification_id', 'token_id', 'token_consumption_id', 'activation_authorization_id', 'adapter_version', 'execution_session_id', 'authority_constraints', 'invocation_descriptor_id', 'activation_result_fingerprint', 'activated_scope', 'activation_result_id', 'authority_reference'}
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
def validate_runtime_adapter_activation_handoff(artifact:Any): return _validate(artifact)
def inspect_runtime_adapter_activation_handoff(artifact:Any):
 r=_validate(artifact); return inspect_result(r.valid,r.errors)
from core.engineering.engineering_runtime_adapter_activation_result import validate_runtime_adapter_activation_result
from core.engineering.engineering_runtime_adapter_activation_verification import validate_runtime_adapter_activation_verification
def build_runtime_adapter_activation_handoff(activation_result, activation_verification, token_consumption=None, controlled_activation=None):
 r=activation_result if isinstance(activation_result,Mapping) else {}; v=activation_verification if isinstance(activation_verification,Mapping) else {}; t=token_consumption if isinstance(token_consumption,Mapping) else {}; c=controlled_activation if isinstance(controlled_activation,Mapping) else {}
 ok=validate_runtime_adapter_activation_result(r).valid and r.get('result_status')=='activated' and validate_runtime_adapter_activation_verification(v).valid and v.get('verification_status')=='verified' and (not t or t.get('consumption_status')=='consumed')
 return _build(ok, ['handoff_ready'] if ok else ['handoff_not_ready'], activation_result_id=r.get('activation_result_id'), activation_result_fingerprint=r.get('fingerprint'), activation_verification_id=v.get('activation_verification_id'), activation_verification_fingerprint=v.get('fingerprint'), controlled_activation_id=r.get('controlled_activation_id'), token_consumption_id=r.get('token_consumption_id'), token_id=r.get('token_id'), activation_authorization_id=(c or t or {}).get('activation_authorization_id'), adapter_id=r.get('adapter_id'), adapter_version=r.get('adapter_version'), execution_session_id=r.get('execution_session_id'), invocation_descriptor_id=r.get('invocation_descriptor_id'), activated_scope=r.get('activated_scope'), authority_reference=(c or {}).get('authority_reference'), authority_constraints=(c or {}).get('authority_constraints'), activation_governance_completed=ok, token_consumed=ok, adapter_loaded=False, adapter_code_executed=False, adapter_invoked=False, runtime_invoked=False, authority_consumed=False, mutation_performed=False)
