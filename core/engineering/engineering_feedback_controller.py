from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_failure_analysis import build_failure_analysis
from core.engineering.engineering_failure_analysis_validation import validate_failure_analysis
from core.engineering.engineering_repair_continuation_eligibility import evaluate_repair_continuation_eligibility
from core.engineering.engineering_repair_continuation_eligibility_validation import validate_repair_continuation_eligibility
from core.engineering.engineering_repair_continuation_cycle import create_repair_continuation_cycle
from core.engineering.engineering_repair_continuation_cycle_validation import validate_repair_continuation_cycle
from core.engineering.engineering_repair_candidate import build_engineering_repair_candidate
from core.engineering.engineering_repair_candidate_validation import validate_engineering_repair_candidate
from core.engineering.engineering_repair_plan import build_engineering_repair_plan
from core.engineering.engineering_repair_plan_validation import validate_engineering_repair_plan
from core.engineering.engineering_change_proposal import assemble_change_proposal
from core.engineering.engineering_completion_foundation import build_proposal_linkage
from core.engineering.engineering_feedback_report import build_feedback_report
from core.engineering.engineering_feedback_persistence import persist_feedback_state, resume_feedback_state

def build_continuation_candidate(*, original_candidate:Mapping[str,Any], original_plan:Mapping[str,Any], failure_analysis:Mapping[str,Any], repository_analysis:Mapping[str,Any]|None=None)->Mapping[str,Any]:
    targets=failure_analysis.get('affected_target_paths') or original_plan.get('allowed_target_paths') or original_candidate.get('target_scope')
    ev=[{'evidence_id':'failure-analysis','evidence_type':'failure_analysis','source_artifact_identity':failure_analysis['failure_analysis_id'],'source_fingerprint':failure_analysis['fingerprint'],'bounded_summary':failure_analysis['bounded_summary']}]
    return build_engineering_repair_candidate(task_id=failure_analysis['task_id'], repository_identity=failure_analysis['repository_identity'], analysis_identity=failure_analysis['failure_analysis_id'], analysis_fingerprint=failure_analysis['fingerprint'], requested_outcome='Repair continuation for failed verification without scope expansion.', defect_classification='test_failure', defect_summary=failure_analysis['bounded_summary'], evidence_references=ev, target_scope=targets, prohibited_scope=original_candidate.get('prohibited_scope') or original_plan.get('prohibited_target_paths') or [], affected_components=original_candidate.get('affected_components') or [], estimated_change_kind=original_candidate.get('estimated_change_kind','replace_file'), risk_level=original_candidate.get('risk_level','medium'), confidence=failure_analysis.get('confidence_level',0.75), selection_status='selected')

def build_continuation_plan(*, candidate:Mapping[str,Any], original_plan:Mapping[str,Any], failure_analysis:Mapping[str,Any])->Mapping[str,Any]:
    exp=[]; ops=[]
    for i,t in enumerate(candidate.get('target_scope') or [],1):
        eid=f'continuation-expectation-{i:02d}'
        exp.append({'expectation_id':eid,'expectation_type':'focused_test_passed','required':True,'expected_status':'satisfied','description':'Focused regression check for failed verification expectation.','target_path':t})
        ops.append({'operation_type':'replace_file','target_path':t,'rationale':'Repair target linked to failure reason '+failure_analysis.get('failure_classification','unknown_failure'),'verification_expectation_ids':[eid],'expected_postcondition':'focused expectation repaired'})
    return build_engineering_repair_plan(candidate=candidate, requested_outcome=candidate['requested_outcome'], ordered_operations=ops, allowed_target_paths=candidate.get('target_scope'), prohibited_target_paths=candidate.get('prohibited_scope'), verification_expectations=exp, constraints=['no shell commands','no git operations','no network operations','human approval required'])

def build_continuation_proposal(*, task_id:str, repository_identity:str, parent_proposal:Mapping[str,Any], parent_session:Mapping[str,Any], execution_result:Mapping[str,Any], verification_result:Mapping[str,Any], failure_analysis:Mapping[str,Any], cycle:Mapping[str,Any], candidate:Mapping[str,Any], repair_plan:Mapping[str,Any])->Mapping[str,Any]:
    payload={'intent':{'task_id':task_id,'repository_identity':repository_identity,'original_proposal_identity':parent_proposal.get('proposal_id'),'failure_analysis_identity':failure_analysis.get('failure_analysis_id'),'repair_continuation_cycle_identity':cycle.get('repair_continuation_cycle_id')},'workspace_evidence':{'workspace_id':'bounded-feedback','workspace_execution_closure_id':execution_result.get('result_id','execution-result'),'upstream_execution_session_id':parent_session.get('execution_session_id')},'target_admissions':[],'scope_policy':{'maximum_affected_files':len(repair_plan.get('allowed_target_paths') or []),'maximum_total_proposed_content_bytes':0},'preconditions':[],'operations':[],'contents':[],'diffs':[],'authority_constraints':['human_approval_required','authorization_not_granted'],'validation_requirements':repair_plan.get('verification_expectations') or []}
    return assemble_change_proposal(payload)

def build_continuation_proposal_linkage(*, task_id:str, repository_identity:str, failure_analysis:Mapping[str,Any], candidate:Mapping[str,Any], repair_plan:Mapping[str,Any], proposal:Mapping[str,Any])->Mapping[str,Any]:
    return build_proposal_linkage(task_id=task_id, repository_identity=repository_identity, analysis=failure_analysis, candidate=candidate, repair_plan=repair_plan, proposal=proposal)

def build_feedback_bundle(**kw:Any)->Mapping[str,Any]:
    analysis=build_failure_analysis(**{k:kw[k] for k in ('execution_result','verification_plan','verification_run','verification_evidence','verification_result','runtime_continuation','original_repair_plan','original_candidate','original_analysis','original_proposal')})
    if not validate_failure_analysis(analysis, verification_result=kw['verification_result'], original_repair_plan=kw['original_repair_plan'], execution_result=kw['execution_result']).valid: raise ValueError('failure_analysis_invalid')
    eligibility=evaluate_repair_continuation_eligibility(failure_analysis=analysis, verification_result=kw['verification_result'], runtime_continuation=kw['runtime_continuation'], task_state=kw.get('task_state'), task_history=kw.get('task_history'))
    if not validate_repair_continuation_eligibility(eligibility, failure_analysis=analysis).valid: raise ValueError('eligibility_invalid')
    candidate=build_continuation_candidate(original_candidate=kw['original_candidate'], original_plan=kw['original_repair_plan'], failure_analysis=analysis)
    plan=build_continuation_plan(candidate=candidate, original_plan=kw['original_repair_plan'], failure_analysis=analysis)
    cycle=create_repair_continuation_cycle(failure_analysis=analysis, eligibility=eligibility, parent_execution_session=kw['parent_execution_session'], parent_proposal=kw['original_proposal'], parent_execution_result=kw['execution_result'], parent_verification_result=kw['verification_result'], new_candidate=candidate, new_plan=plan)
    proposal=build_continuation_proposal(task_id=analysis['task_id'], repository_identity=analysis['repository_identity'], parent_proposal=kw['original_proposal'], parent_session=kw['parent_execution_session'], execution_result=kw['execution_result'], verification_result=kw['verification_result'], failure_analysis=analysis, cycle=cycle, candidate=candidate, repair_plan=plan)
    linkage=build_continuation_proposal_linkage(task_id=analysis['task_id'], repository_identity=analysis['repository_identity'], failure_analysis=analysis, candidate=candidate, repair_plan=plan, proposal=proposal)
    cycle=create_repair_continuation_cycle(failure_analysis=analysis, eligibility=eligibility, parent_execution_session=kw['parent_execution_session'], parent_proposal=kw['original_proposal'], parent_execution_result=kw['execution_result'], parent_verification_result=kw['verification_result'], new_candidate=candidate, new_plan=plan, new_proposal=proposal, new_proposal_linkage=linkage)
    report=build_feedback_report(failure_analysis=analysis, eligibility=eligibility, continuation_cycle=cycle, candidate=candidate, plan=plan, proposal=proposal, proposal_linkage=linkage)
    return {'failure_analysis':analysis,'eligibility':eligibility,'candidate':candidate,'plan':plan,'proposal':proposal,'proposal_linkage':linkage,'cycle':cycle,'report':report,'status':'awaiting_human_approval'}

def resume_repair_continuation(state:Mapping[str,Any])->Mapping[str,Any]: return resume_feedback_state(state)
def inspect_repair_continuation(state:Mapping[str,Any])->Mapping[str,Any]: return dict(state)
def attach_continuation_proposal(*, failure_analysis, eligibility, continuation_cycle, candidate, plan, proposal, proposal_linkage): return persist_feedback_state(failure_analysis=failure_analysis, eligibility=eligibility, continuation_cycle=continuation_cycle, candidate=candidate, plan=plan, proposal=proposal, proposal_linkage=proposal_linkage)
