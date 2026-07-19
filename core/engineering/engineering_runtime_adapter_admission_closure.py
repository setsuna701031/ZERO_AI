from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_runtime_adapter_admission_common import *
from core.engineering.engineering_runtime_adapter_admission_request import validate_runtime_adapter_admission_request
from core.engineering.engineering_runtime_adapter_admission_policy import validate_runtime_adapter_admission_policy
from core.engineering.engineering_runtime_adapter_admission_eligibility import validate_runtime_adapter_admission_eligibility
from core.engineering.engineering_runtime_adapter_admission import validate_runtime_adapter_admission
SCHEMA='zero.engineering.runtime_adapter_admission_closure.v1';ID='closure_id';PREFIX='engineering-runtime-adapter-admission-closure-'
FIELDS={'request_result','policy_result','eligibility_result','admission_result','linkage_valid','boundary_valid','passive_only_invariant','mutation_prohibition','runtime_invocation_prohibition','authority_consumption_prohibition','package_status'}
def build_runtime_adapter_admission_closure(request:Mapping[str,Any],policy:Mapping[str,Any],eligibility:Mapping[str,Any],admission:Mapping[str,Any])->dict[str,Any]:
 rv=validate_runtime_adapter_admission_request(request).valid; pv=validate_runtime_adapter_admission_policy(policy).valid; ev=validate_runtime_adapter_admission_eligibility(eligibility).valid; av=validate_runtime_adapter_admission(admission).valid
 linkage=eligibility.get('request_id')==request.get('request_id') and admission.get('request_id')==request.get('request_id') and admission.get('eligibility_id')==eligibility.get('eligibility_id') and admission.get('policy_id')==policy.get('policy_id')
 b=all(x.get('boundary')==boundary() for x in (request,policy,eligibility,admission) if isinstance(x,Mapping))
 status='closed' if all((rv,pv,ev,av,linkage,b)) else ('invalid' if not any((rv,pv,ev,av)) else 'not_closed')
 return stable_artifact({'schema':SCHEMA,'request_result':rv,'policy_result':pv,'eligibility_result':eligibility.get('eligibility_status','invalid') if ev else 'invalid','admission_result':admission.get('admission_status','invalid') if av else 'invalid','linkage_valid':linkage,'boundary_valid':b,'passive_only_invariant':True,'mutation_prohibition':True,'runtime_invocation_prohibition':True,'authority_consumption_prohibition':True,'package_status':status,'boundary':boundary()},ID,PREFIX)
def validate_runtime_adapter_admission_closure(v:Any)->ValidationResult: return validate_artifact(v,schema=SCHEMA,statuses={'closed','not_closed','invalid'},id_key=ID,prefix=PREFIX,fields=FIELDS)
def inspect_runtime_adapter_admission_closure(v:Any)->dict[str,Any]:
 r=validate_runtime_adapter_admission_closure(v); return {'schema':SCHEMA,'valid':r.valid,'package_status':v.get('package_status') if isinstance(v,Mapping) else 'invalid','reason_codes':list(r.errors)}
