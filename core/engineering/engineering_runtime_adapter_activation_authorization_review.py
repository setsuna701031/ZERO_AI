from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_runtime_adapter_activation_authorization_common import *
from core.engineering.engineering_runtime_adapter_activation_authorization_request import validate_runtime_adapter_activation_authorization_request
from core.engineering.engineering_runtime_adapter_activation_authorization_policy import validate_runtime_adapter_activation_authorization_policy
SCHEMA='zero.engineering.runtime_adapter_activation_authorization_review.v1';ID='activation_authorization_review_id';PREFIX='engineering-runtime-adapter-activation-authorization-review-'
FIELDS={'activation_authorization_request_id','activation_authorization_request_fingerprint','activation_authorization_policy_id','activation_authorization_policy_fingerprint','review_status','reason_codes','approved'}
def evaluate_runtime_adapter_activation_authorization_review(request:Mapping[str,Any],policy:Mapping[str,Any])->dict[str,Any]:
 reasons=[]
 rr=validate_runtime_adapter_activation_authorization_request(request); pr=validate_runtime_adapter_activation_authorization_policy(policy)
 if not rr.valid: reasons.append('invalid_activation_authorization_request'); reasons+=list(rr.errors)
 if not pr.valid: reasons.append('invalid_activation_authorization_policy'); reasons+=list(pr.errors)
 status='approved' if not reasons else ('invalid' if 'invalid_activation_authorization_request' in reasons or 'invalid_activation_authorization_policy' in reasons else 'not_approved')
 return stable_artifact({'schema':SCHEMA,'activation_authorization_request_id':request.get('activation_authorization_request_id'),'activation_authorization_request_fingerprint':request.get('fingerprint'),'activation_authorization_policy_id':policy.get('activation_authorization_policy_id'),'activation_authorization_policy_fingerprint':policy.get('fingerprint'),'review_status':status,'reason_codes':normalize_reasons(reasons),'approved':status=='approved'},ID,PREFIX)
def validate_runtime_adapter_activation_authorization_review(v:Any)->ValidationResult:
 r=validate_artifact(v,schema=SCHEMA,id_key=ID,prefix=PREFIX,fields=FIELDS,status_key='review_status',statuses={'approved','not_approved','invalid'}); e=list(r.errors)
 if isinstance(v,Mapping):
  if v.get('approved') is not (v.get('review_status')=='approved'): e.append('passive_invariant_violation')
  if normalize_reasons(v.get('reason_codes',[]))!=list(v.get('reason_codes',[])): e.append('reason_codes_not_normalized')
 return ValidationResult(not e,tuple(dict.fromkeys(e)))
def inspect_runtime_adapter_activation_authorization_review(v:Any)->dict[str,Any]:
 r=validate_runtime_adapter_activation_authorization_review(v); return {'schema':SCHEMA,'valid':r.valid,'review_status':v.get('review_status') if isinstance(v,Mapping) else 'invalid','reason_codes':list(r.errors)}
