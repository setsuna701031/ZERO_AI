from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_planning_common import freeze, norm_path, path_ok, seal, short_text

SCHEMA='zero.engineering.failure_analysis.v1'
CLASSIFICATIONS=('test_assertion_failure','syntax_failure','static_policy_failure','missing_expected_file','unexpected_file_present','invalid_json','verification_timeout','verification_runner_error','execution_output_mismatch','insufficient_evidence','scope_conflict','unknown_failure')
REPAIRABILITY=('repairable','possibly_repairable','not_repairable','blocked_by_scope','blocked_by_authority','insufficient_evidence','manual_only')
AUTHORITY_BOUNDARY={'approval':'not_granted','authorization':'not_granted','token':'not_granted','mutation':'not_granted','verification':'not_granted','shell':'not_granted','git':'not_granted','network':'not_granted'}

def _identity(a:Mapping[str,Any], *names:str)->Any:
    for n in names:
        if a.get(n) is not None: return a.get(n)
    return a.get('artifact_identity')
def _fp(a:Mapping[str,Any])->Any: return a.get('fingerprint') or a.get('artifact_fingerprint')
def _failed_expectations(v:Mapping[str,Any])->list[str]:
    return sorted(x.get('expectation_id') for x in v.get('verification_expectation_results',[]) if isinstance(x,Mapping) and x.get('status') in ('failed','blocked','invalid','not_verified'))
def _derive_classification(v:Mapping[str,Any], run:Mapping[str,Any]) -> str:
    text=' '.join(str(x).lower() for x in [v.get('test_summary',''),v.get('compilation_summary',''),v.get('static_inspection_summary',''),run.get('runner_status',''),run.get('run_status',''),*v.get('reason_codes',[])])
    if v.get('verification_status')=='blocked': return 'insufficient_evidence' if 'evidence' in text else 'scope_conflict' if 'scope' in text else 'verification_runner_error'
    if 'syntax' in text or 'compile' in text: return 'syntax_failure'
    if 'policy' in text: return 'static_policy_failure'
    if 'missing' in text: return 'missing_expected_file'
    if 'unexpected' in text: return 'unexpected_file_present'
    if 'json' in text: return 'invalid_json'
    if 'timeout' in text: return 'verification_timeout'
    if 'runner' in text: return 'verification_runner_error'
    return 'test_assertion_failure' if _failed_expectations(v) else 'unknown_failure'
def _derive_repairability(cls:str, v:Mapping[str,Any]) -> str:
    reasons=set(v.get('reason_codes') or [])
    if cls=='insufficient_evidence': return 'insufficient_evidence'
    if 'manual_only' in reasons: return 'manual_only'
    if 'authority_expansion_required' in reasons: return 'blocked_by_authority'
    if cls=='scope_conflict': return 'blocked_by_scope'
    return 'repairable' if cls in {'test_assertion_failure','syntax_failure','missing_expected_file','unexpected_file_present','invalid_json','execution_output_mismatch'} else 'possibly_repairable'

def build_failure_analysis(*, execution_result:Mapping[str,Any], verification_plan:Mapping[str,Any], verification_run:Mapping[str,Any], verification_evidence:Any, verification_result:Mapping[str,Any], runtime_continuation:Mapping[str,Any], original_repair_plan:Mapping[str,Any], original_candidate:Mapping[str,Any], original_analysis:Mapping[str,Any], original_proposal:Mapping[str,Any]) -> Mapping[str,Any]:
    cls=_derive_classification(verification_result, verification_run); failed=_failed_expectations(verification_result)
    targets=sorted(dict.fromkeys(norm_path(p) for p in (verification_result.get('verified_target_paths') or original_repair_plan.get('allowed_target_paths') or [])))
    ops=sorted(dict.fromkeys(str(x) for x in (verification_result.get('verified_operation_ids') or original_repair_plan.get('ordered_operation_ids') or [])))
    ev=[]
    for e in list(verification_evidence or verification_result.get('evidence_references') or [])[:32]:
        if isinstance(e,Mapping):
            d={'evidence_id':short_text(e.get('evidence_id','evidence'),96),'source_artifact_identity':short_text(e.get('source_artifact_identity',_identity(verification_result,'verification_result_id')),160),'source_fingerprint':short_text(e.get('source_fingerprint',_fp(verification_result)),80),'bounded_summary':short_text(e.get('bounded_summary','bounded verification evidence reference'),640)}
            if e.get('repository_relative_path') is not None: d['repository_relative_path']=norm_path(e.get('repository_relative_path'))
            ev.append(d)
    body={'schema':SCHEMA,'task_id':verification_result.get('task_id'),'repository_identity':verification_result.get('repository_identity'),'execution_session_id':verification_plan.get('execution_session_id') or runtime_continuation.get('execution_session_id'),'original_analysis_identity':_identity(original_analysis,'repository_analysis_report_id'),'original_analysis_fingerprint':_fp(original_analysis),'original_candidate_identity':_identity(original_candidate,'candidate_id'),'original_candidate_fingerprint':_fp(original_candidate),'original_plan_identity':_identity(original_repair_plan,'repair_plan_id'),'original_plan_fingerprint':_fp(original_repair_plan),'original_proposal_identity':_identity(original_proposal,'proposal_id'),'original_proposal_fingerprint':_fp(original_proposal),'execution_result_identity':_identity(execution_result,'result_id','execution_id'),'execution_result_fingerprint':_fp(execution_result),'verification_plan_identity':_identity(verification_plan,'verification_plan_id'),'verification_plan_fingerprint':_fp(verification_plan),'verification_run_identity':_identity(verification_run,'verification_run_id'),'verification_run_fingerprint':_fp(verification_run),'verification_result_identity':_identity(verification_result,'verification_result_id'),'verification_result_fingerprint':_fp(verification_result),'runtime_continuation_identity':_identity(runtime_continuation,'runtime_continuation_id'),'runtime_continuation_fingerprint':_fp(runtime_continuation),'failure_classification':cls,'failed_expectation_ids':failed,'failed_step_ids':sorted(str(x) for x in verification_run.get('failed_step_ids',failed)),'affected_operation_ids':ops,'affected_target_paths':targets,'evidence_references':sorted(ev,key=lambda x:x['evidence_id']),'root_cause_hypotheses':[cls],'confidence_level':0.75 if ev else 0.25,'repairability':_derive_repairability(cls,verification_result),'reason_codes':sorted(dict.fromkeys([cls,*verification_result.get('reason_codes',[])])),'bounded_summary':short_text(f'Bounded failure analysis derived from verification result {_identity(verification_result,"verification_result_id")}.',640),'deterministic':True,'immutable':True,'authority_boundary':AUTHORITY_BOUNDARY}
    return seal(body,'failure_analysis_id','engineering-failure-analysis')
