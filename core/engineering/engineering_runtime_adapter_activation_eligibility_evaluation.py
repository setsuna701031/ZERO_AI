from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_runtime_adapter_activation_eligibility_common import *
from core.engineering.engineering_runtime_adapter_activation_eligibility_request import validate_runtime_adapter_activation_eligibility_request
from core.engineering.engineering_runtime_adapter_activation_eligibility_policy import validate_runtime_adapter_activation_eligibility_policy
from core.engineering.engineering_runtime_adapter_activation_constraint_profile import validate_runtime_adapter_activation_constraint_profile
SCHEMA='zero.engineering.runtime_adapter_activation_eligibility_evaluation.v1';ID='activation_eligibility_evaluation_id';PREFIX='engineering-runtime-adapter-activation-eligibility-evaluation-'
FIELDS={'activation_eligibility_request_id','activation_eligibility_request_fingerprint','activation_eligibility_policy_id','activation_eligibility_policy_fingerprint','activation_constraint_profile_id','activation_constraint_profile_fingerprint','preparation_review_handoff_id','preparation_review_handoff_fingerprint','preparation_review_id','preparation_review_fingerprint','preparation_review_closure_id','preparation_review_closure_fingerprint','preparation_id','preparation_closure_id','invocation_descriptor_id','runtime_adapter_admission_id','adapter_id','adapter_version','eligibility_status','reason_codes'}
def _reasons(req,pol,prof):
 e=[]; rr=validate_runtime_adapter_activation_eligibility_request(req); pr=validate_runtime_adapter_activation_eligibility_policy(pol); cr=validate_runtime_adapter_activation_constraint_profile(prof)
 if not rr.valid: e.append('invalid_activation_eligibility_request'); e+=list(rr.errors)
 if not pr.valid: e.append('invalid_activation_eligibility_policy')
 if not cr.valid: e.append('invalid_activation_constraint_profile'); e+=list(cr.errors)
 if isinstance(req,Mapping) and isinstance(prof,Mapping):
  pairs=[('activation_eligibility_request_id','activation_eligibility_request_id','review_handoff_linkage_mismatch'),('fingerprint','activation_eligibility_request_fingerprint','review_handoff_linkage_mismatch'),('preparation_review_handoff_id','preparation_review_handoff_id','review_handoff_linkage_mismatch'),('preparation_review_handoff_fingerprint','preparation_review_handoff_fingerprint','review_handoff_linkage_mismatch'),('adapter_id','adapter_id','adapter_identity_mismatch'),('adapter_version','adapter_version','adapter_version_mismatch')]
  for a,b,c in pairs:
   if req.get(a)!=prof.get(b): e.append(c)
 if contains_prohibited(req) or contains_prohibited(prof): e.append('executable_payload')
 if contains_credential_like(req) or contains_credential_like(prof): e.append('credential_like_payload')
 return normalize_reasons(e)
def evaluate_runtime_adapter_activation_eligibility(request:Mapping[str,Any],policy:Mapping[str,Any],profile:Mapping[str,Any])->dict[str,Any]:
 reasons=_reasons(request,policy,profile); status='eligible' if not reasons else ('invalid' if any(r.startswith('invalid_activation') or r.startswith('missing:') or r in ('artifact_not_object','identity_mismatch') for r in reasons) else 'ineligible')
 return stable_artifact({'schema':SCHEMA,'activation_eligibility_request_id':request.get('activation_eligibility_request_id'),'activation_eligibility_request_fingerprint':request.get('fingerprint'),'activation_eligibility_policy_id':policy.get('activation_eligibility_policy_id'),'activation_eligibility_policy_fingerprint':policy.get('fingerprint'),'activation_constraint_profile_id':profile.get('activation_constraint_profile_id'),'activation_constraint_profile_fingerprint':profile.get('fingerprint'),'preparation_review_handoff_id':request.get('preparation_review_handoff_id'),'preparation_review_handoff_fingerprint':request.get('preparation_review_handoff_fingerprint'),'preparation_review_id':request.get('preparation_review_id'),'preparation_review_fingerprint':request.get('preparation_review_fingerprint'),'preparation_review_closure_id':request.get('preparation_review_closure_id'),'preparation_review_closure_fingerprint':request.get('preparation_review_closure_fingerprint'),'preparation_id':request.get('preparation_id'),'preparation_closure_id':request.get('preparation_closure_id'),'invocation_descriptor_id':request.get('invocation_descriptor_id'),'runtime_adapter_admission_id':request.get('runtime_adapter_admission_id'),'adapter_id':request.get('adapter_id'),'adapter_version':request.get('adapter_version'),'eligibility_status':status,'reason_codes':reasons},ID,PREFIX)
def validate_runtime_adapter_activation_eligibility_evaluation(v:Any)->ValidationResult:
 r=validate_artifact(v,schema=SCHEMA,id_key=ID,prefix=PREFIX,fields=FIELDS,status_key='eligibility_status',statuses={'eligible','ineligible','invalid'}); return r
def inspect_runtime_adapter_activation_eligibility_evaluation(v:Any)->dict[str,Any]:
 r=validate_runtime_adapter_activation_eligibility_evaluation(v); return {'schema':SCHEMA,'valid':r.valid,'eligibility_status':v.get('eligibility_status') if isinstance(v,Mapping) else 'invalid','reason_codes':list(r.errors)}
