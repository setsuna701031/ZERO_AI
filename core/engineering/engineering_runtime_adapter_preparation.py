from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_runtime_adapter_preparation_common import *
from core.engineering.engineering_runtime_adapter_preparation_request import validate_runtime_adapter_preparation_request
from core.engineering.engineering_runtime_adapter_preparation_policy import validate_runtime_adapter_preparation_policy
from core.engineering.engineering_runtime_adapter_preparation_eligibility import validate_runtime_adapter_preparation_eligibility
from core.engineering.engineering_runtime_adapter_invocation_descriptor import validate_runtime_adapter_invocation_descriptor, INV
SCHEMA='zero.engineering.runtime_adapter_preparation.v1';ID='preparation_id';PREFIX='engineering-runtime-adapter-preparation-'
FIELDS={'preparation_request_id','preparation_request_fingerprint','preparation_policy_id','preparation_policy_fingerprint','preparation_eligibility_id','preparation_eligibility_fingerprint','invocation_descriptor_id','invocation_descriptor_fingerprint','runtime_adapter_admission_id','runtime_adapter_admission_fingerprint','engineering_runtime_handoff_id','execution_session_id','adapter_id','adapter_version','prepared_scope','preparation_status','reason_codes','passive_only','adapter_invoked','runtime_invoked','executor_invoked','scheduler_invoked','authority_consumed','mutation_performed'}
PINV={k:v for k,v in INV.items() if k!='executable' and k!='adapter_loaded'}
def build_runtime_adapter_preparation(request:Mapping[str,Any],policy:Mapping[str,Any],eligibility:Mapping[str,Any],descriptor:Mapping[str,Any])->dict[str,Any]:
 reasons=[]
 if not validate_runtime_adapter_preparation_request(request).valid: reasons.append('invalid_request')
 if not validate_runtime_adapter_preparation_policy(policy).valid: reasons.append('invalid_policy')
 if not validate_runtime_adapter_preparation_eligibility(eligibility).valid: reasons.append('invalid_eligibility')
 if not validate_runtime_adapter_invocation_descriptor(descriptor).valid: reasons.append('invalid_descriptor')
 if eligibility.get('eligibility_status')!='eligible': reasons.extend(eligibility.get('reason_codes',[]) or ['not_eligible'])
 if descriptor.get('preparation_request_id')!=request.get('preparation_request_id') or descriptor.get('preparation_request_fingerprint')!=request.get('fingerprint'): reasons.append('request_linkage_mismatch')
 if descriptor.get('preparation_eligibility_id')!=eligibility.get('preparation_eligibility_id') or descriptor.get('preparation_eligibility_fingerprint')!=eligibility.get('fingerprint'): reasons.append('eligibility_linkage_mismatch')
 if eligibility.get('preparation_policy_id')!=policy.get('preparation_policy_id') or eligibility.get('preparation_policy_fingerprint')!=policy.get('fingerprint'): reasons.append('policy_linkage_mismatch')
 if request.get('runtime_adapter_admission_status')!='admitted': reasons.append('admission_not_admitted')
 if not all(descriptor.get(k) is v for k,v in INV.items()): reasons.append('passive_invariant_violation')
 status='invalid' if any(r.startswith('invalid') for r in reasons) else ('not_prepared' if reasons else 'prepared')
 return stable_artifact({'schema':SCHEMA,'preparation_request_id':request.get('preparation_request_id'),'preparation_request_fingerprint':request.get('fingerprint'),'preparation_policy_id':policy.get('preparation_policy_id'),'preparation_policy_fingerprint':policy.get('fingerprint'),'preparation_eligibility_id':eligibility.get('preparation_eligibility_id'),'preparation_eligibility_fingerprint':eligibility.get('fingerprint'),'invocation_descriptor_id':descriptor.get('invocation_descriptor_id'),'invocation_descriptor_fingerprint':descriptor.get('fingerprint'),'runtime_adapter_admission_id':request.get('runtime_adapter_admission_id'),'runtime_adapter_admission_fingerprint':request.get('runtime_adapter_admission_fingerprint'),'engineering_runtime_handoff_id':request.get('engineering_runtime_handoff_id'),'execution_session_id':request.get('execution_session_id'),'adapter_id':request.get('requested_adapter_id'),'adapter_version':request.get('requested_adapter_version'),'prepared_scope':descriptor.get('prepared_scope') if status=='prepared' else {},'preparation_status':status,'reason_codes':normalize_reasons(reasons),**PINV},ID,PREFIX)
def validate_runtime_adapter_preparation(v:Any)->ValidationResult: return validate_artifact(v,schema=SCHEMA,statuses={'prepared','not_prepared','invalid'},id_key=ID,prefix=PREFIX,fields=FIELDS)
def inspect_runtime_adapter_preparation(v:Any)->dict[str,Any]:
 r=validate_runtime_adapter_preparation(v); return {'schema':SCHEMA,'valid':r.valid,'preparation_status':v.get('preparation_status') if isinstance(v,Mapping) else 'invalid','reason_codes':list(r.errors)}
