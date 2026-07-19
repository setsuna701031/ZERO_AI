from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_runtime_adapter_admission_common import *
from core.engineering.engineering_runtime_adapter_admission_request import validate_runtime_adapter_admission_request
SCHEMA='zero.engineering.runtime_adapter_admission_eligibility.v1';ID='eligibility_id';PREFIX='engineering-runtime-adapter-admission-eligibility-'
FIELDS={'request_id','request_fingerprint','eligibility_status','reason_codes','linkage'}
def evaluate_runtime_adapter_admission_eligibility(request:Mapping[str,Any],handoff:Mapping[str,Any],session:Mapping[str,Any],admission:Mapping[str,Any])->dict[str,Any]:
 reasons=[]
 if not validate_runtime_adapter_admission_request(request).valid: reasons.append('invalid_request')
 if handoff.get('schema')!='zero.engineering.runtime_handoff.v1' or not handoff.get('engineering_runtime_handoff_id') or not handoff.get('fingerprint'): reasons.append('invalid_handoff')
 if request.get('engineering_runtime_handoff_id')!=handoff.get('engineering_runtime_handoff_id'): reasons.append('handoff_id_mismatch')
 if request.get('engineering_runtime_handoff_fingerprint')!=handoff.get('fingerprint'): reasons.append('handoff_fingerprint_mismatch')
 if request.get('execution_session_id')!=session.get('engineering_execution_session_id'): reasons.append('session_id_mismatch')
 if request.get('execution_session_fingerprint')!=session.get('fingerprint'): reasons.append('session_fingerprint_mismatch')
 if request.get('governed_execution_admission_id')!=admission.get('engineering_execution_admission_id'): reasons.append('governed_admission_id_mismatch')
 if request.get('governed_execution_admission_fingerprint')!=admission.get('fingerprint'): reasons.append('governed_admission_fingerprint_mismatch')
 if not canonical_nonempty(request.get('requested_adapter_id')): reasons.append('empty_adapter_id')
 if not canonical_nonempty(request.get('requested_adapter_version')): reasons.append('empty_adapter_version')
 if not scope_bounded(request.get('requested_scope'),session.get('sealed_scope',admission.get('admitted_scope',{}))): reasons.append('scope_expansion')
 if not authority_valid(request.get('authority_constraints'),request.get('requested_scope')): reasons.append('authority_constraints_invalid')
 if contains_prohibited(request) or contains_prohibited(handoff) or contains_prohibited(session) or contains_prohibited(admission): reasons.append('prohibited_payload')
 if any(str(x.get('status',x.get('admission_decision',''))).lower() in TERMINAL_STATES for x in (handoff,session,admission) if isinstance(x,Mapping)): reasons.append('terminal_upstream_state')
 status='invalid' if any(r.startswith('invalid') for r in reasons) else ('ineligible' if reasons else 'eligible')
 return stable_artifact({'schema':SCHEMA,'request_id':request.get('request_id'),'request_fingerprint':request.get('fingerprint'),'eligibility_status':status,'reason_codes':sorted(set(reasons)),'linkage':{'handoff':request.get('engineering_runtime_handoff_id')==handoff.get('engineering_runtime_handoff_id'),'session':request.get('execution_session_id')==session.get('engineering_execution_session_id'),'governed_admission':request.get('governed_execution_admission_id')==admission.get('engineering_execution_admission_id')},'boundary':boundary()},ID,PREFIX)
def validate_runtime_adapter_admission_eligibility(v:Any)->ValidationResult: return validate_artifact(v,schema=SCHEMA,statuses={'eligible','ineligible','invalid'},id_key=ID,prefix=PREFIX,fields=FIELDS)
def inspect_runtime_adapter_admission_eligibility(v:Any)->dict[str,Any]:
 r=validate_runtime_adapter_admission_eligibility(v); return {'schema':SCHEMA,'valid':r.valid,'eligibility_status':v.get('eligibility_status') if isinstance(v,Mapping) else 'invalid','reason_codes':list(r.errors)}
