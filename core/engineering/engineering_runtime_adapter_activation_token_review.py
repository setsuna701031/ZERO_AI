from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_runtime_adapter_activation_token_common import *
from core.engineering.engineering_runtime_adapter_activation_token_eligibility import validate_runtime_adapter_activation_token_eligibility
from core.engineering.engineering_runtime_adapter_activation_token_preparation import validate_runtime_adapter_activation_token_preparation
REQ_SCHEMA='zero.engineering.runtime_adapter_activation_token_review_request.v1';SCHEMA='zero.engineering.runtime_adapter_activation_token_review.v1';REQ_ID='token_review_request_id';ID='token_review_id';REQ_PREFIX='engineering-runtime-adapter-activation-token-review-request-';PREFIX='engineering-runtime-adapter-activation-token-review-'
REQ_FIELDS={'token_preparation_id','token_preparation_fingerprint','token_eligibility_id','token_eligibility_fingerprint','activation_authorization_handoff_id','activation_authorization_id','adapter_id','adapter_version','execution_session_id','invocation_descriptor_id','authorized_scope','requested_token_scope','max_uses','token_constraints','authority_reference','authority_constraints'}
FIELDS=REQ_FIELDS|{REQ_ID,'token_review_request_fingerprint','review_status','reason_codes','passive_only','token_material_present','adapter_loaded','adapter_activated','adapter_invoked','runtime_invoked','authority_consumed','mutation_performed'}
def build_runtime_adapter_activation_token_review_request(preparation:Mapping[str,Any],eligibility:Mapping[str,Any])->dict[str,Any]:
 return stable_artifact({'schema':REQ_SCHEMA,'token_preparation_id':preparation.get('token_preparation_id'),'token_preparation_fingerprint':preparation.get('fingerprint'),'token_eligibility_id':eligibility.get('token_eligibility_id'),'token_eligibility_fingerprint':eligibility.get('fingerprint'),'activation_authorization_handoff_id':preparation.get('activation_authorization_handoff_id'),'activation_authorization_id':preparation.get('activation_authorization_id'),'adapter_id':preparation.get('adapter_id'),'adapter_version':preparation.get('adapter_version'),'execution_session_id':eligibility.get('execution_session_id'),'invocation_descriptor_id':eligibility.get('invocation_descriptor_id'),'authorized_scope':preparation.get('authorized_scope'),'requested_token_scope':preparation.get('prepared_token_scope'),'max_uses':preparation.get('max_uses'),'token_constraints':preparation.get('token_constraints'),'authority_reference':preparation.get('authority_reference'),'authority_constraints':preparation.get('authority_constraints')},REQ_ID,REQ_PREFIX)
def validate_runtime_adapter_activation_token_review_request(v:Any)->ValidationResult:
 r=validate_artifact(v,schema=REQ_SCHEMA,id_key=REQ_ID,prefix=REQ_PREFIX,fields=REQ_FIELDS); e=list(r.errors)
 if isinstance(v,Mapping) and not (scope_bounded(v.get('requested_token_scope'),v.get('authorized_scope')) and v.get('max_uses')==1 and token_constraints_valid(v.get('token_constraints'),v.get('requested_token_scope')) and authority_valid(v.get('authority_constraints'),v.get('authorized_scope'))): e.append('invalid_review_bounds')
 return ValidationResult(not e,tuple(dict.fromkeys(e)))
def inspect_runtime_adapter_activation_token_review_request(v:Any)->dict[str,Any]:
 r=validate_runtime_adapter_activation_token_review_request(v); return {'schema':REQ_SCHEMA,'valid':r.valid,'reason_codes':list(r.errors)}
def evaluate_runtime_adapter_activation_token_review(request:Mapping[str,Any],preparation:Mapping[str,Any],eligibility:Mapping[str,Any])->dict[str,Any]:
 rv=validate_runtime_adapter_activation_token_review_request(request).valid; pv=validate_runtime_adapter_activation_token_preparation(preparation).valid; ev=validate_runtime_adapter_activation_token_eligibility(eligibility).valid
 linked=request.get('token_preparation_id')==preparation.get('token_preparation_id') and request.get('token_preparation_fingerprint')==preparation.get('fingerprint') and request.get('token_eligibility_id')==eligibility.get('token_eligibility_id') and request.get('token_eligibility_fingerprint')==eligibility.get('fingerprint')
 ok=rv and pv and ev and linked and preparation.get('preparation_status')=='prepared' and eligibility.get('eligibility_status')=='eligible'
 reasons=[] if ok else ['token_review_not_approved']
 body={k:request.get(k) for k in REQ_FIELDS}; body.update({'schema':SCHEMA,REQ_ID:request.get(REQ_ID),'token_review_request_fingerprint':request.get('fingerprint'),'review_status':'approved' if ok else ('invalid' if not (rv and pv and ev) else 'not_approved'),'reason_codes':normalize_reasons(reasons),'passive_only':True,'token_material_present':False,'adapter_loaded':False,'adapter_activated':False,'adapter_invoked':False,'runtime_invoked':False,'authority_consumed':False,'mutation_performed':False})
 return stable_artifact(body,ID,PREFIX)
def validate_runtime_adapter_activation_token_review(v:Any)->ValidationResult:
 r=validate_artifact(v,schema=SCHEMA,id_key=ID,prefix=PREFIX,fields=FIELDS,status_key='review_status',statuses={'approved','not_approved','invalid'}); e=list(r.errors)
 if isinstance(v,Mapping) and not passive_invariants_valid(v): e.append('passive_invariant_violation')
 return ValidationResult(not e,tuple(dict.fromkeys(e)))
def inspect_runtime_adapter_activation_token_review(v:Any)->dict[str,Any]:
 r=validate_runtime_adapter_activation_token_review(v); return {'schema':SCHEMA,'valid':r.valid,'review_status':v.get('review_status') if isinstance(v,Mapping) else 'invalid','reason_codes':list(r.errors)}
