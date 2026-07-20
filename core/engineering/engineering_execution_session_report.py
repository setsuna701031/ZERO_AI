from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_mutation_transaction_common import fingerprint
from core.engineering.engineering_execution_session import REPORT_SCHEMA, AUTHORITY_BOUNDARY, validate_engineering_execution_session, REFS

def _fp_body(a): return fingerprint({k:v for k,v in a.items() if k!='fingerprint'})
def build_execution_session_report(session: Mapping[str, Any]) -> dict[str, Any]:
    r=validate_engineering_execution_session(session)
    if not r['valid']: raise ValueError('invalid_session')
    refs={name+'_reference': {'identity':session.get(ik),'fingerprint':session.get(fk)} for name,(ik,fk) in REFS.items() if name not in {'proposal_linkage','authorized_scope'}}
    body={'schema':REPORT_SCHEMA,'execution_session_id':session.get('execution_session_id'),'task_id':session.get('task_id'),'repository_identity':session.get('repository_identity'),'session_status':session.get('session_status'),'current_stage':session.get('current_stage'),**refs,'operation_count':session.get('bounded_summary',{}).get('operation_count',0),'target_count':session.get('bounded_summary',{}).get('target_count',0),'verification_expectation_count':session.get('bounded_summary',{}).get('verification_expectation_count',0),'execution_status':'accepted' if session.get('execution_identity') else 'absent','verification_status':'accepted' if session.get('verification_result_identity') else 'absent','completion_status':'accepted' if session.get('completion_identity') else 'absent','closure_status':'accepted' if session.get('closure_identity') else 'absent','replay_count':session.get('replay_count',0),'resume_count':session.get('resume_count',0),'stage_history_summary':[x['stage'] for x in session.get('stage_history',[])],'evidence_summary':'bounded metadata only','blocked_reason_codes':list(session.get('blocked_reason_codes',[])),'failure_reason_codes':list(session.get('failure_reason_codes',[])),'deterministic':True,'immutable':True,'authority_boundary':dict(AUTHORITY_BOUNDARY)}
    body['report_id']='engineering-execution-session-report-'+fingerprint(body)[:24]; body['fingerprint']=_fp_body(body); return body
def validate_execution_session_report(value: Any) -> Any:
    e=[]
    if not isinstance(value, Mapping): return {'valid':False,'errors':['artifact_not_mapping']}
    if value.get('schema')!=REPORT_SCHEMA: e.append('schema_mismatch')
    if value.get('authority_boundary')!=AUTHORITY_BOUNDARY: e.append('authority_boundary_invalid')
    if value.get('fingerprint')!=_fp_body(value): e.append('fingerprint_mismatch')
    return {'valid':not e,'errors':e}
