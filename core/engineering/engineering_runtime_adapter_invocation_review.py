from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_invocation_common import *

REQ_SCHEMA='zero.engineering.runtime_adapter_invocation_review_request.v1'; REQ_ID='invocation_review_request_id'; REQ_PREFIX='rtrevreq-'; SCHEMA='zero.engineering.runtime_adapter_invocation_review.v1'; ID_KEY='invocation_review_id'; PREFIX='rtrev-'; STATUS_KEY='review_status'; STATUSES={'approved','not_approved','invalid'}
REQ_FIELDS=set('invocation_preparation_id invocation_preparation_fingerprint invocation_admission_id invocation_admission_fingerprint invocation_intake_id invocation_intake_fingerprint activation_handoff_id adapter_id adapter_version execution_session_id invocation_descriptor_id review_scope operation input_bindings expected_output_contract authority_reference authority_constraints'.split())
FIELDS=REQ_FIELDS|set('invocation_review_request_id invocation_review_request_fingerprint review_status reason_codes adapter_loaded adapter_code_executed adapter_invoked runtime_invoked executor_invoked scheduler_invoked authority_consumed mutation_performed'.split())
def build_runtime_adapter_invocation_review_request(preparation, admission, intake):
 p=preparation if isinstance(preparation,Mapping) else {}; a=admission if isinstance(admission,Mapping) else {}; i=intake if isinstance(intake,Mapping) else {}
 return stable_artifact({'schema':REQ_SCHEMA,'invocation_preparation_id':p.get('invocation_preparation_id'),'invocation_preparation_fingerprint':p.get('fingerprint'),'invocation_admission_id':a.get('invocation_admission_id'),'invocation_admission_fingerprint':a.get('fingerprint'),'invocation_intake_id':i.get('invocation_intake_id'),'invocation_intake_fingerprint':i.get('fingerprint'),'activation_handoff_id':p.get('activation_handoff_id'),'adapter_id':p.get('adapter_id'),'adapter_version':p.get('adapter_version'),'execution_session_id':p.get('execution_session_id'),'invocation_descriptor_id':p.get('invocation_descriptor_id'),'review_scope':p.get('prepared_invocation_scope'),'operation':p.get('operation'),'input_bindings':p.get('input_bindings'),'expected_output_contract':p.get('expected_output_contract'),'authority_reference':p.get('authority_reference'),'authority_constraints':p.get('authority_constraints')},REQ_ID,REQ_PREFIX)
def validate_runtime_adapter_invocation_review_request(v):
 r=validate_artifact(v,schema=REQ_SCHEMA,id_key=REQ_ID,prefix=REQ_PREFIX,fields=REQ_FIELDS); extra=validate_common_invocation(v) if isinstance(v,Mapping) else []
 return ValidationResult(r.valid and not extra, tuple(list(r.errors)+extra))
def inspect_runtime_adapter_invocation_review_request(v):
 r=validate_runtime_adapter_invocation_review_request(v); return inspect_result(r.valid,r.errors)
def evaluate_runtime_adapter_invocation_review(request, preparation, admission, intake):
 q=request if isinstance(request,Mapping) else {}; p=preparation if isinstance(preparation,Mapping) else {}; a=admission if isinstance(admission,Mapping) else {}; i=intake if isinstance(intake,Mapping) else {}
 ok=validate_runtime_adapter_invocation_review_request(q).valid and p.get('preparation_status')=='prepared' and a.get('admission_status')=='admitted' and i.get('intake_status')=='accepted' and q.get('invocation_preparation_fingerprint')==p.get('fingerprint')
 st='approved' if ok else ('invalid' if not isinstance(request,Mapping) else 'not_approved')
 return stable_artifact({'schema':SCHEMA,**{k:q.get(k) for k in REQ_FIELDS},'invocation_review_request_id':q.get('invocation_review_request_id'),'invocation_review_request_fingerprint':q.get('fingerprint'),'review_status':st,'reason_codes':normalize_reasons([st]),'adapter_loaded':False,'adapter_code_executed':False,'adapter_invoked':False,'runtime_invoked':False,'executor_invoked':False,'scheduler_invoked':False,'authority_consumed':False,'mutation_performed':False},ID_KEY,PREFIX)
def validate_runtime_adapter_invocation_review(v):
 r=validate_artifact(v,schema=SCHEMA,id_key=ID_KEY,prefix=PREFIX,fields=FIELDS,status_key=STATUS_KEY,statuses=STATUSES); extra=validate_common_invocation(v) if isinstance(v,Mapping) else []
 return ValidationResult(r.valid and not extra, tuple(list(r.errors)+extra))
def inspect_runtime_adapter_invocation_review(v):
 r=validate_runtime_adapter_invocation_review(v); return inspect_result(r.valid,r.errors)
