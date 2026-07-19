from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_runtime_adapter_preparation_review_common import *
from core.engineering.engineering_runtime_adapter_preparation_review_request import validate_runtime_adapter_preparation_review_request
from core.engineering.engineering_runtime_adapter_preparation_review_policy import validate_runtime_adapter_preparation_review_policy
SCHEMA='zero.engineering.runtime_adapter_preparation_review_eligibility.v1';ID='review_eligibility_id';PREFIX='engineering-runtime-adapter-preparation-review-eligibility-'
FIELDS={'review_request_id','review_request_fingerprint','review_policy_id','review_policy_fingerprint','runtime_adapter_preparation_id','runtime_adapter_preparation_fingerprint','runtime_adapter_preparation_closure_id','runtime_adapter_preparation_closure_fingerprint','invocation_descriptor_id','invocation_descriptor_fingerprint','preparation_request_id','preparation_request_fingerprint','preparation_policy_id','preparation_policy_fingerprint','preparation_eligibility_id','preparation_eligibility_fingerprint','runtime_adapter_admission_id','runtime_adapter_admission_fingerprint','adapter_id','adapter_version','eligibility_status','reason_codes'}
def _reasons(request:Mapping[str,Any],policy:Mapping[str,Any])->list[str]:
 reasons=[]
 if not validate_runtime_adapter_preparation_review_request(request).valid: reasons.append('invalid_review_request')
 if not validate_runtime_adapter_preparation_review_policy(policy).valid: reasons.append('invalid_review_policy')
 if request.get('runtime_adapter_preparation_status')!='prepared': reasons.append('preparation_not_prepared')
 if request.get('runtime_adapter_preparation_closure_status')!='closed': reasons.append('closure_not_closed')
 if not canonical_nonempty(request.get('runtime_adapter_preparation_id')) or not canonical_nonempty(request.get('runtime_adapter_preparation_fingerprint')): reasons.append('preparation_linkage_mismatch')
 if not canonical_nonempty(request.get('runtime_adapter_preparation_closure_id')) or not canonical_nonempty(request.get('runtime_adapter_preparation_closure_fingerprint')): reasons.append('closure_linkage_mismatch')
 if not canonical_nonempty(request.get('invocation_descriptor_id')) or not canonical_nonempty(request.get('invocation_descriptor_fingerprint')): reasons.append('descriptor_linkage_mismatch')
 for key,code in (('preparation_request_id','preparation_request_linkage_mismatch'),('preparation_policy_id','preparation_policy_linkage_mismatch'),('preparation_eligibility_id','preparation_eligibility_linkage_mismatch'),('runtime_adapter_admission_id','admission_linkage_mismatch')):
  if not canonical_nonempty(request.get(key)): reasons.append(code)
 if not canonical_nonempty(request.get('adapter_id')): reasons.append('adapter_identity_mismatch')
 if not canonical_nonempty(request.get('adapter_version')): reasons.append('adapter_version_mismatch')
 if contains_wildcard(request.get('prepared_scope')): reasons.append('wildcard_scope')
 if not scope_bounded(request.get('authority_constraints',{}).get('scope') if isinstance(request.get('authority_constraints'),Mapping) else None,request.get('prepared_scope')): reasons.append('scope_expansion')
 if not authority_valid(request.get('authority_constraints'),request.get('prepared_scope')):
  a=request.get('authority_constraints',{}) if isinstance(request.get('authority_constraints'),Mapping) else {}
  for k,val,code in (('non_transferable',True,'transferable_authority'),('non_reusable',True,'reusable_authority'),('scope_bound',True,'unbounded_authority'),('perpetual',False,'perpetual_authority'),('passive',True,'active_authority'),('consumed',False,'consumed_authority'),('closed',False,'closed_authority'),('unrestricted',False,'unrestricted_authority'),('restricted',True,'unrestricted_authority')):
   if a.get(k) is not val: reasons.append(code)
 if contains_prohibited(request): reasons.extend(['executable_payload','credential_like_payload'])
 return normalize_reasons(reasons)
def evaluate_runtime_adapter_preparation_review_eligibility(request:Mapping[str,Any],policy:Mapping[str,Any])->dict[str,Any]:
 reasons=_reasons(request,policy); status='invalid' if 'invalid_review_request' in reasons or 'invalid_review_policy' in reasons else ('ineligible' if reasons else 'eligible')
 return stable_artifact({'schema':SCHEMA,'review_request_id':request.get('review_request_id'),'review_request_fingerprint':request.get('fingerprint'),'review_policy_id':policy.get('review_policy_id'),'review_policy_fingerprint':policy.get('fingerprint'),'runtime_adapter_preparation_id':request.get('runtime_adapter_preparation_id'),'runtime_adapter_preparation_fingerprint':request.get('runtime_adapter_preparation_fingerprint'),'runtime_adapter_preparation_closure_id':request.get('runtime_adapter_preparation_closure_id'),'runtime_adapter_preparation_closure_fingerprint':request.get('runtime_adapter_preparation_closure_fingerprint'),'invocation_descriptor_id':request.get('invocation_descriptor_id'),'invocation_descriptor_fingerprint':request.get('invocation_descriptor_fingerprint'),'preparation_request_id':request.get('preparation_request_id'),'preparation_request_fingerprint':request.get('preparation_request_fingerprint'),'preparation_policy_id':request.get('preparation_policy_id'),'preparation_policy_fingerprint':request.get('preparation_policy_fingerprint'),'preparation_eligibility_id':request.get('preparation_eligibility_id'),'preparation_eligibility_fingerprint':request.get('preparation_eligibility_fingerprint'),'runtime_adapter_admission_id':request.get('runtime_adapter_admission_id'),'runtime_adapter_admission_fingerprint':request.get('runtime_adapter_admission_fingerprint'),'adapter_id':request.get('adapter_id'),'adapter_version':request.get('adapter_version'),'eligibility_status':status,'reason_codes':reasons},ID,PREFIX)
def validate_runtime_adapter_preparation_review_eligibility(v:Any)->ValidationResult: return validate_artifact(v,schema=SCHEMA,statuses={'eligible','ineligible','invalid'},id_key=ID,prefix=PREFIX,fields=FIELDS,status_key='eligibility_status')
def inspect_runtime_adapter_preparation_review_eligibility(v:Any)->dict[str,Any]:
 r=validate_runtime_adapter_preparation_review_eligibility(v); return {'schema':SCHEMA,'valid':r.valid,'eligibility_status':v.get('eligibility_status') if isinstance(v,Mapping) else 'invalid','reason_codes':list(r.errors)}
