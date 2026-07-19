from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_runtime_adapter_admission_common import *
from core.engineering.engineering_runtime_adapter_admission_request import validate_runtime_adapter_admission_request
from core.engineering.engineering_runtime_adapter_admission_eligibility import validate_runtime_adapter_admission_eligibility
from core.engineering.engineering_runtime_adapter_admission_policy import validate_runtime_adapter_admission_policy
SCHEMA='zero.engineering.runtime_adapter_admission.v1';ID='admission_id';PREFIX='engineering-runtime-adapter-admission-'
FIELDS={'request_id','request_fingerprint','eligibility_id','eligibility_fingerprint','policy_id','policy_fingerprint','engineering_runtime_handoff_id','engineering_runtime_handoff_fingerprint','execution_session_id','requested_adapter_id','requested_adapter_version','admitted_scope','authority_constraints','admission_status','reason_codes'}
def build_runtime_adapter_admission(request:Mapping[str,Any],eligibility:Mapping[str,Any],policy:Mapping[str,Any])->dict[str,Any]:
 reasons=[]
 if not validate_runtime_adapter_admission_request(request).valid: reasons.append('invalid_request')
 if not validate_runtime_adapter_admission_eligibility(eligibility).valid: reasons.append('invalid_eligibility')
 if not validate_runtime_adapter_admission_policy(policy).valid: reasons.append('invalid_policy')
 if eligibility.get('request_id')!=request.get('request_id') or eligibility.get('request_fingerprint')!=request.get('fingerprint'): reasons.append('request_eligibility_mismatch')
 if eligibility.get('eligibility_status')!='eligible': reasons.extend(eligibility.get('reason_codes',[]) or ['not_eligible'])
 if not authority_valid(request.get('authority_constraints'),request.get('requested_scope')): reasons.append('authority_constraints_invalid')
 status='invalid' if any(r.startswith('invalid') for r in reasons) else ('not_admitted' if reasons else 'admitted')
 return stable_artifact({'schema':SCHEMA,'request_id':request.get('request_id'),'request_fingerprint':request.get('fingerprint'),'eligibility_id':eligibility.get('eligibility_id'),'eligibility_fingerprint':eligibility.get('fingerprint'),'policy_id':policy.get('policy_id'),'policy_fingerprint':policy.get('fingerprint'),'engineering_runtime_handoff_id':request.get('engineering_runtime_handoff_id'),'engineering_runtime_handoff_fingerprint':request.get('engineering_runtime_handoff_fingerprint'),'execution_session_id':request.get('execution_session_id'),'requested_adapter_id':request.get('requested_adapter_id'),'requested_adapter_version':request.get('requested_adapter_version'),'admitted_scope':request.get('requested_scope') if status=='admitted' else {},'authority_constraints':request.get('authority_constraints',{}),'admission_status':status,'reason_codes':sorted(set(reasons)),'boundary':boundary()},ID,PREFIX)
def validate_runtime_adapter_admission(v:Any)->ValidationResult: return validate_artifact(v,schema=SCHEMA,statuses={'admitted','not_admitted','invalid'},id_key=ID,prefix=PREFIX,fields=FIELDS)
def inspect_runtime_adapter_admission(v:Any)->dict[str,Any]:
 r=validate_runtime_adapter_admission(v); return {'schema':SCHEMA,'valid':r.valid,'admission_status':v.get('admission_status') if isinstance(v,Mapping) else 'invalid','reason_codes':list(r.errors)}
