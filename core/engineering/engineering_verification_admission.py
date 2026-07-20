from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_mutation_transaction_common import fingerprint
from core.engineering.engineering_verification_plan import ALLOWED_TYPES, AUTHORITY_BOUNDARY
from core.engineering.engineering_verification_plan_validation import validate_verification_plan
SCHEMA='zero.engineering.verification_admission.v1'; RUNNER_IDENTITY='zero.engineering.governed_verification_runner.v1'
def _fp_body(a): return fingerprint({k:v for k,v in a.items() if k!='fingerprint'})
def build_verification_admission(plan:Mapping[str,Any], *, runner_identity:str=RUNNER_IDENTITY, admission_status:str|None=None)->dict[str,Any]:
    r=validate_verification_plan(plan); status=admission_status or ('admitted' if r.valid else 'invalid')
    body={'schema':SCHEMA,'verification_plan_identity':plan.get('verification_plan_id'),'verification_plan_fingerprint':plan.get('fingerprint'),'execution_session_id':plan.get('execution_session_id'),'execution_result_identity':plan.get('execution_result_identity'),'runner_identity':runner_identity,'allowed_verification_types':sorted(set(s.get('verification_type') for s in plan.get('verification_steps') or [] if isinstance(s,Mapping)) & set(ALLOWED_TYPES)),'allowed_target_paths':list(plan.get('allowed_target_paths') or []),'maximum_duration_seconds':plan.get('maximum_duration_seconds'),'maximum_output_bytes':plan.get('maximum_output_bytes'),'maximum_evidence_items':plan.get('maximum_evidence_items'),'single_use':True,'admission_status':status,'status':status,'consumed':False,'deterministic':True,'immutable':True,'authority_boundary':dict(AUTHORITY_BOUNDARY),'reason_codes':list(r.errors)}
    body['verification_admission_id']='engineering-verification-admission-'+fingerprint(body)[:24]; body['fingerprint']=_fp_body(body); return body
