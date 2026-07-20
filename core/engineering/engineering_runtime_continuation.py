from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_mutation_transaction_common import fingerprint
from core.engineering.engineering_verification_plan import AUTHORITY_BOUNDARY
SCHEMA='zero.engineering.runtime_continuation.v1'; DECISIONS={'continue_to_completion','remain_blocked','verification_failed','manual_intervention_required','invalid'}
def _fp_body(a): return fingerprint({k:v for k,v in a.items() if k!='fingerprint'})
def build_runtime_continuation(*, session:Mapping[str,Any], execution_result:Mapping[str,Any], verification_result:Mapping[str,Any], verification_run:Mapping[str,Any]|None=None)->dict[str,Any]:
    st=verification_result.get('verification_status') or verification_result.get('status'); runst=(verification_run or {}).get('run_status')
    if st=='passed': dec='continue_to_completion'; nxt='completion_eligible'; mi=False; eligible=True; reasons=[]
    elif runst=='runner_error': dec='manual_intervention_required'; nxt='blocked'; mi=True; eligible=False; reasons=['runner_error']
    elif runst in {'blocked','invalid'} or st in {'blocked','not_verified'}: dec='remain_blocked'; nxt='blocked'; mi=True; eligible=False; reasons=[runst or st]
    elif st=='failed': dec='verification_failed'; nxt='verification_failed'; mi=False; eligible=False; reasons=['verification_failed']
    else: dec='invalid'; nxt='failed'; mi=True; eligible=False; reasons=['invalid_verification_result']
    body={'schema':SCHEMA,'execution_session_id':session.get('execution_session_id'),'execution_result_identity':execution_result.get('result_id') or execution_result.get('execution_id') or execution_result.get('artifact_identity'),'verification_result_identity':verification_result.get('verification_result_id'),'verification_result_fingerprint':verification_result.get('fingerprint'),'decision':dec,'status':dec,'reason_codes':reasons,'next_allowed_stage':nxt,'completion_eligible':eligible,'retry_eligible':False,'manual_intervention_required':mi,'deterministic':True,'immutable':True,'authority_boundary':dict(AUTHORITY_BOUNDARY)}
    body['runtime_continuation_id']='engineering-runtime-continuation-'+fingerprint(body)[:24]; body['fingerprint']=_fp_body(body); return body
