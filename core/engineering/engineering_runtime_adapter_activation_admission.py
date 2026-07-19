from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_activation_common import *
SCHEMA='zero.engineering.runtime_adapter_activation_admission.v1'
ID_KEY='activation_admission_id'
PREFIX='rtaa-'
STATUS_KEY='admission_status'
STATUSES={'admitted', 'not_admitted', 'invalid'}
BASE_FIELDS={'token_id', 'token_authorization_id', 'activation_authorization_id', 'execution_session_id', 'invocation_descriptor_id', 'token_issuance_id', 'activation_admission_request_id', 'token_verification_fingerprint', 'adapter_version', 'authority_constraints', 'token_fingerprint', 'authority_reference', 'token_verification_id', 'token_handoff_id', 'activation_admission_request_fingerprint', 'activation_scope', 'token_handoff_fingerprint', 'adapter_id', 'activation_authorization_handoff_id'}
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
def validate_runtime_adapter_activation_admission(artifact:Any): return _validate(artifact)
def inspect_runtime_adapter_activation_admission(artifact:Any):
 r=_validate(artifact); return inspect_result(r.valid,r.errors)
REQ_SCHEMA='zero.engineering.runtime_adapter_activation_admission_request.v1'; POL_SCHEMA='zero.engineering.runtime_adapter_activation_admission_policy.v1'
def build_runtime_adapter_activation_admission_request(token_handoff, activation_scope=None, admission_context=None):
 h=token_handoff if isinstance(token_handoff,Mapping) else {}; scope=activation_scope if activation_scope is not None else h.get('activation_scope',h.get('token_scope',h.get('authorized_scope',{})))
 body={'schema':REQ_SCHEMA,'token_handoff_id':h.get('token_handoff_id'),'token_handoff_fingerprint':h.get('fingerprint'),'token_id':h.get('token_id'),'token_fingerprint':h.get('token_fingerprint'),'token_issuance_id':h.get('token_issuance_id'),'token_verification_id':h.get('token_verification_id'),'token_verification_fingerprint':h.get('token_verification_fingerprint'),'token_authorization_id':h.get('token_authorization_id'),'activation_authorization_handoff_id':h.get('activation_authorization_handoff_id'),'activation_authorization_id':h.get('activation_authorization_id',h.get('token_authorization_id')),'adapter_id':h.get('adapter_id'),'adapter_version':h.get('adapter_version'),'execution_session_id':h.get('execution_session_id'),'invocation_descriptor_id':h.get('invocation_descriptor_id'),'activation_scope':scope,'max_uses':h.get('max_uses',1),'current_uses':h.get('current_uses',0),'authority_reference':h.get('authority_reference'),'authority_constraints':h.get('authority_constraints',{'valid':True,'consumed':False,'passive':True,'scope':scope}),'activation_constraints':h.get('activation_constraints',{}),'admission_context':admission_context or {},'request_input_fingerprint':canonical_fingerprint({'token_handoff':h,'activation_scope':scope,'admission_context':admission_context or {}})}
 return stable_artifact(body,'activation_admission_request_id','rtaar-')
def validate_runtime_adapter_activation_admission_request(a): return validate_artifact(a,schema=REQ_SCHEMA,id_key='activation_admission_request_id',prefix='rtaar-',fields=set(a.keys())-{'schema','activation_admission_request_id','fingerprint'} if isinstance(a,Mapping) else set())
def inspect_runtime_adapter_activation_admission_request(a):
 r=validate_runtime_adapter_activation_admission_request(a); return inspect_result(r.valid,r.errors)
def build_default_runtime_adapter_activation_admission_policy(): return stable_artifact({'schema':POL_SCHEMA,'requires_issued_unconsumed':True,'max_uses':1,'current_uses':0,'passive_only':True},'activation_admission_policy_id','rtaap-')
def validate_runtime_adapter_activation_admission_policy(p): return validate_artifact(p,schema=POL_SCHEMA,id_key='activation_admission_policy_id',prefix='rtaap-',fields={'requires_issued_unconsumed','max_uses','current_uses','passive_only'})
def inspect_runtime_adapter_activation_admission_policy(p):
 r=validate_runtime_adapter_activation_admission_policy(p); return inspect_result(r.valid,r.errors)
def build_runtime_adapter_activation_admission(request, policy=None, token_handoff=None):
 r=request if isinstance(request,Mapping) else {}; h=token_handoff if isinstance(token_handoff,Mapping) else {}; reasons=[]
 ok=validate_runtime_adapter_activation_admission_request(r).valid and (policy is None or validate_runtime_adapter_activation_admission_policy(policy).valid) and r.get('max_uses')==1 and r.get('current_uses')==0 and not contains_wildcard(r.get('activation_scope')) and authority_valid(r.get('authority_constraints'),r.get('activation_scope'))
 for k,v in {'eligible_for_adapter_activation_admission':True,'activation_authorized':True,'token_issued':True,'token_verified':True,'token_consumed':False,'token_material_present':False,'adapter_loaded':False,'adapter_activated':False,'adapter_invoked':False,'runtime_invoked':False,'authority_consumed':False,'mutation_performed':False}.items():
  if h and h.get(k) is not v: ok=False; reasons.append(k+'_mismatch')
 if h and h.get('token_state','issued_unconsumed')!='issued_unconsumed': ok=False; reasons.append('token_state_invalid')
 return _build('admitted' if ok else 'not_admitted', reasons or ['admitted'], **{k:r.get(k) for k in BASE_FIELDS if k not in {'activation_admission_request_id','activation_admission_request_fingerprint'}}, activation_admission_request_id=r.get('activation_admission_request_id'), activation_admission_request_fingerprint=r.get('fingerprint'), activation_admission_policy_id=(policy or {}).get('activation_admission_policy_id') if isinstance(policy,Mapping) else None, activation_admission_policy_fingerprint=(policy or {}).get('fingerprint') if isinstance(policy,Mapping) else None)
