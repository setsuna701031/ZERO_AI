from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_mutation_transaction_common import fingerprint
from core.engineering.engineering_planning_common import ValidationResult, authority_errors, fp_ok, id_ok, path_ok, result, subset, no_overlap, short_text

PROPOSAL_LINKAGE_SCHEMA='zero.engineering.proposal_linkage.v1'
VERIFICATION_RESULT_SCHEMA='zero.engineering.verification_result.v1'
COMPLETION_SCHEMA='zero.engineering.completion.v1'
VERIFICATION_STATUSES=('passed','failed','blocked','invalid','not_verified')
COMPLETION_STATUSES=('completed','not_completed','blocked','failed','invalid')
AUTHORITY_BOUNDARY={'approval':'not_granted','authorization':'not_granted','token':'not_granted','mutation':'not_granted','test_execution':'not_granted','verification':'not_granted','git':'not_granted'}
SUCCESS_VERIFICATION_STATUSES=('passed',)
SUCCESS_COMPLETION_STATUSES=('completed',)
_MAX_SUMMARY=640
_MAX_EVIDENCE=32

def _fp_body(a:Mapping[str,Any])->str: return fingerprint({k:v for k,v in a.items() if k!='fingerprint'})
def _exp_ids(plan:Mapping[str,Any])->list[str]:
    if plan.get('verification_expectation_ids') is not None: return list(plan.get('verification_expectation_ids') or [])
    return [x.get('expectation_id') for x in plan.get('verification_expectations') or [] if isinstance(x,Mapping)]
def _mandatory_exp_ids(plan:Mapping[str,Any])->list[str]:
    if plan.get('verification_expectation_ids') is not None: return list(plan.get('verification_expectation_ids') or [])
    return [x.get('expectation_id') for x in plan.get('verification_expectations') or [] if isinstance(x,Mapping) and x.get('required') is True]
def _target_paths(plan:Mapping[str,Any])->list[str]:
    if plan.get('ordered_operations') is None: return list(plan.get('allowed_target_paths') or [])
    return sorted(dict.fromkeys(o.get('target_path') for o in plan.get('ordered_operations') or [] if isinstance(o,Mapping) and o.get('target_path')))
def _execution_identity(execution:Mapping[str,Any])->Any: return execution.get('result_id') or execution.get('execution_id') or execution.get('artifact_identity')
def _execution_fingerprint(execution:Mapping[str,Any])->Any: return execution.get('fingerprint') or execution.get('artifact_fingerprint')
def _proposal_identity(proposal:Mapping[str,Any])->Any: return proposal.get('proposal_id') or proposal.get('artifact_identity')
def _proposal_fingerprint(proposal:Mapping[str,Any])->Any: return proposal.get('fingerprint') or proposal.get('artifact_fingerprint')

def build_proposal_linkage(*, task_id:str, repository_identity:Any, analysis:Mapping[str,Any], candidate:Mapping[str,Any], repair_plan:Mapping[str,Any], proposal:Mapping[str,Any])->dict[str,Any]:
    body={'schema':PROPOSAL_LINKAGE_SCHEMA,'status':'linked','task_id':task_id,'repository_identity':repository_identity,'analysis_identity':analysis.get('repository_analysis_report_id') or analysis.get('artifact_identity') or repair_plan.get('analysis_identity'),'analysis_fingerprint':analysis.get('fingerprint') or analysis.get('artifact_fingerprint'), 'candidate_identity':candidate.get('candidate_id') or candidate.get('artifact_identity') or repair_plan.get('candidate_identity'),'candidate_fingerprint':candidate.get('fingerprint') or candidate.get('artifact_fingerprint') or repair_plan.get('candidate_fingerprint'),'repair_plan_identity':repair_plan.get('repair_plan_id'),'repair_plan_fingerprint':repair_plan.get('fingerprint'),'proposal_identity':_proposal_identity(proposal),'proposal_fingerprint':_proposal_fingerprint(proposal),'ordered_operation_ids':list(repair_plan.get('ordered_operation_ids') or []),'operation_count':repair_plan.get('operation_count'),'allowed_target_paths':list(repair_plan.get('allowed_target_paths') or []),'prohibited_target_paths':list(repair_plan.get('prohibited_target_paths') or []),'verification_expectation_ids':_exp_ids(repair_plan),'deterministic':True,'immutable':True,'authority_boundary':AUTHORITY_BOUNDARY}
    body['proposal_linkage_id']='engineering-proposal-linkage-'+fingerprint(body)[:24]
    body['fingerprint']=_fp_body(body)
    return body

def validate_proposal_linkage(value:Any, *, task_id:str|None=None, repository_identity:Any=None, analysis:Mapping[str,Any]|None=None, candidate:Mapping[str,Any]|None=None, repair_plan:Mapping[str,Any]|None=None, proposal:Mapping[str,Any]|None=None)->ValidationResult:
    e=[]
    if not isinstance(value,Mapping): return ValidationResult(False,('artifact_not_mapping',))
    if value.get('schema')!=PROPOSAL_LINKAGE_SCHEMA: e.append('schema_mismatch')
    if value.get('status')!='linked': e.append('status_invalid')
    if not id_ok(value.get('proposal_linkage_id'),'engineering-proposal-linkage'): e.append('proposal_linkage_id_malformed')
    if not fp_ok(value.get('fingerprint')) or value.get('fingerprint')!=_fp_body(value): e.append('fingerprint_mismatch')
    if value.get('deterministic') is not True or value.get('immutable') is not True: e.append('determinism_immutability_invalid')
    if value.get('authority_boundary')!=AUTHORITY_BOUNDARY: e.append('authority_boundary_invalid')
    if task_id and value.get('task_id')!=task_id: e.append('task_id_mismatch')
    if repository_identity is not None and value.get('repository_identity')!=repository_identity: e.append('repository_identity_mismatch')
    if analysis:
        if value.get('analysis_identity')!=(analysis.get('repository_analysis_report_id') or analysis.get('artifact_identity')): e.append('analysis_identity_mismatch')
        if value.get('analysis_fingerprint')!=(analysis.get('fingerprint') or analysis.get('artifact_fingerprint')): e.append('analysis_fingerprint_mismatch')
    if candidate:
        if value.get('candidate_identity')!=(candidate.get('candidate_id') or candidate.get('artifact_identity')): e.append('candidate_identity_mismatch')
        if value.get('candidate_fingerprint')!=(candidate.get('fingerprint') or candidate.get('artifact_fingerprint')): e.append('candidate_fingerprint_mismatch')
    if repair_plan:
        for k,src in [('repair_plan_identity','repair_plan_id'),('repair_plan_fingerprint','fingerprint'),('operation_count','operation_count')]:
            if value.get(k)!=repair_plan.get(src): e.append(k+'_mismatch')
        if value.get('ordered_operation_ids')!=list(repair_plan.get('ordered_operation_ids') or []): e.append('operation_order_mismatch')
        if not subset(value.get('allowed_target_paths') or [], repair_plan.get('allowed_target_paths') or []): e.append('allowed_scope_expanded')
        if not set(repair_plan.get('prohibited_target_paths') or []).issubset(set(value.get('prohibited_target_paths') or [])): e.append('prohibited_scope_removed')
        if value.get('verification_expectation_ids')!=_exp_ids(repair_plan): e.append('verification_expectation_mismatch')
    if proposal:
        if value.get('proposal_identity')!=_proposal_identity(proposal): e.append('proposal_identity_mismatch')
        if value.get('proposal_fingerprint')!=_proposal_fingerprint(proposal): e.append('proposal_fingerprint_mismatch')
    for k in ('ordered_operation_ids','allowed_target_paths','prohibited_target_paths','verification_expectation_ids'):
        if not isinstance(value.get(k),list): e.append(k+'_invalid')
    if isinstance(value.get('allowed_target_paths'),list) and any(not path_ok(x) for x in value['allowed_target_paths']): e.append('allowed_target_path_invalid')
    if isinstance(value.get('prohibited_target_paths'),list) and any(not path_ok(x) for x in value['prohibited_target_paths']): e.append('prohibited_target_path_invalid')
    if isinstance(value.get('allowed_target_paths'),list) and isinstance(value.get('prohibited_target_paths'),list) and not no_overlap(value['allowed_target_paths'],value['prohibited_target_paths']): e.append('scope_overlap')
    e += authority_errors(value)
    return result(e)

def build_verification_result(*, task_id:str, repository_identity:Any, proposal:Mapping[str,Any], repair_plan:Mapping[str,Any], execution_result:Mapping[str,Any], verification_status:str, verification_expectation_results:list[Mapping[str,Any]], test_summary:str='', compilation_summary:str='', static_inspection_summary:str='', evidence_references:list[Mapping[str,Any]]|None=None, verified_operation_ids:list[str]|None=None, verified_target_paths:list[str]|None=None)->dict[str,Any]:
    exp=[]
    for x in sorted(verification_expectation_results, key=lambda y:y.get('expectation_id','')):
        exp.append({'expectation_id':str(x.get('expectation_id')),'expectation_type':str(x.get('expectation_type')),'status':str(x.get('status')),'summary':short_text(x.get('summary','recorded'),_MAX_SUMMARY),'evidence_reference_ids':sorted(dict.fromkeys(str(r) for r in x.get('evidence_reference_ids',[])))})
    body={'schema':VERIFICATION_RESULT_SCHEMA,'task_id':task_id,'repository_identity':repository_identity,'proposal_identity':_proposal_identity(proposal),'proposal_fingerprint':_proposal_fingerprint(proposal),'repair_plan_identity':repair_plan.get('repair_plan_id'),'repair_plan_fingerprint':repair_plan.get('fingerprint'),'execution_identity':_execution_identity(execution_result),'execution_fingerprint':_execution_fingerprint(execution_result),'verification_status':verification_status,'status':verification_status,'verification_expectation_results':exp,'test_summary':short_text(test_summary or 'not executed by artifact builder',_MAX_SUMMARY),'compilation_summary':short_text(compilation_summary or 'not executed by artifact builder',_MAX_SUMMARY),'static_inspection_summary':short_text(static_inspection_summary or 'not executed by artifact builder',_MAX_SUMMARY),'evidence_references':list(evidence_references or []),'verified_operation_ids':list(verified_operation_ids if verified_operation_ids is not None else repair_plan.get('ordered_operation_ids') or []),'verified_target_paths':list(verified_target_paths if verified_target_paths is not None else _target_paths(repair_plan)),'deterministic':True,'immutable':True,'authority_boundary':AUTHORITY_BOUNDARY}
    body['verification_result_id']='engineering-verification-result-'+fingerprint(body)[:24]
    body['fingerprint']=_fp_body(body)
    return body

def validate_verification_result(value:Any, *, task_id:str|None=None, repository_identity:Any=None, proposal:Mapping[str,Any]|None=None, repair_plan:Mapping[str,Any]|None=None, execution_result:Mapping[str,Any]|None=None)->ValidationResult:
    e=[]
    if not isinstance(value,Mapping): return ValidationResult(False,('artifact_not_mapping',))
    if value.get('schema')!=VERIFICATION_RESULT_SCHEMA: e.append('schema_mismatch')
    if not id_ok(value.get('verification_result_id'),'engineering-verification-result'): e.append('verification_result_id_malformed')
    if not fp_ok(value.get('fingerprint')) or value.get('fingerprint')!=_fp_body(value): e.append('fingerprint_mismatch')
    if value.get('verification_status') not in VERIFICATION_STATUSES or value.get('status')!=value.get('verification_status'): e.append('status_invalid')
    if value.get('deterministic') is not True or value.get('immutable') is not True: e.append('determinism_immutability_invalid')
    if value.get('authority_boundary')!=AUTHORITY_BOUNDARY: e.append('authority_boundary_invalid')
    if task_id and value.get('task_id')!=task_id: e.append('task_id_mismatch')
    if repository_identity is not None and value.get('repository_identity')!=repository_identity: e.append('repository_identity_mismatch')
    if proposal and (value.get('proposal_identity')!=_proposal_identity(proposal) or value.get('proposal_fingerprint')!=_proposal_fingerprint(proposal)): e.append('proposal_linkage_mismatch')
    if repair_plan:
        if value.get('repair_plan_identity')!=repair_plan.get('repair_plan_id') or value.get('repair_plan_fingerprint')!=repair_plan.get('fingerprint'): e.append('plan_linkage_mismatch')
        if value.get('verified_operation_ids')!=list(repair_plan.get('ordered_operation_ids') or []): e.append('operation_linkage_mismatch')
        if value.get('verified_target_paths')!=_target_paths(repair_plan): e.append('target_linkage_mismatch')
        expected=_exp_ids(repair_plan); mandatory=set(_mandatory_exp_ids(repair_plan)); got=[x.get('expectation_id') for x in value.get('verification_expectation_results') or [] if isinstance(x,Mapping)]
        if got!=expected: e.append('expectation_order_or_membership_mismatch')
        if not mandatory.issubset(set(got)): e.append('mandatory_expectation_missing')
    if execution_result and (value.get('execution_identity')!=_execution_identity(execution_result) or value.get('execution_fingerprint')!=_execution_fingerprint(execution_result)): e.append('execution_linkage_mismatch')
    refs=value.get('evidence_references')
    if not isinstance(refs,list) or len(refs)>_MAX_EVIDENCE: e.append('evidence_references_invalid')
    exp=value.get('verification_expectation_results')
    if not isinstance(exp,list): e.append('expectation_results_invalid')
    else:
        ids=[]
        for x in exp:
            if not isinstance(x,Mapping): e.append('expectation_result_malformed'); continue
            ids.append(x.get('expectation_id'))
            if x.get('status') not in VERIFICATION_STATUSES: e.append('expectation_status_invalid')
            if not isinstance(x.get('summary'),str) or len(x.get('summary'))>_MAX_SUMMARY: e.append('summary_unbounded')
            if not isinstance(x.get('evidence_reference_ids'),list) or len(x.get('evidence_reference_ids'))>_MAX_EVIDENCE: e.append('evidence_reference_ids_invalid')
        if len(ids)!=len(set(ids)): e.append('duplicate_expectation')
    e += authority_errors(value)
    return result(e)

def build_completion(*, task_id:str, repository_identity:Any, analysis_identity:str, candidate_identity:str, repair_plan:Mapping[str,Any], proposal:Mapping[str,Any], verification_result:Mapping[str,Any], completion_status:str='completed', completion_summary:str='Engineering lifecycle completed by governed record.', closure_eligibility:bool=True)->dict[str,Any]:
    body={'schema':COMPLETION_SCHEMA,'task_id':task_id,'repository_identity':repository_identity,'analysis_identity':analysis_identity,'candidate_identity':candidate_identity,'repair_plan_identity':repair_plan.get('repair_plan_id'),'proposal_identity':_proposal_identity(proposal),'verification_result_identity':verification_result.get('verification_result_id') or verification_result.get('artifact_identity'),'proposal_fingerprint':_proposal_fingerprint(proposal),'verification_result_fingerprint':verification_result.get('fingerprint') or verification_result.get('artifact_fingerprint'),'completion_status':completion_status,'status':completion_status,'completion_summary':short_text(completion_summary,_MAX_SUMMARY),'closure_eligibility':bool(closure_eligibility),'deterministic':True,'immutable':True,'authority_boundary':AUTHORITY_BOUNDARY}
    body['completion_id']='engineering-completion-'+fingerprint(body)[:24]
    body['fingerprint']=_fp_body(body)
    return body

def validate_completion(value:Any, *, task_id:str|None=None, repository_identity:Any=None, proposal:Mapping[str,Any]|None=None, verification_result:Mapping[str,Any]|None=None)->ValidationResult:
    e=[]
    if not isinstance(value,Mapping): return ValidationResult(False,('artifact_not_mapping',))
    if value.get('schema')!=COMPLETION_SCHEMA: e.append('schema_mismatch')
    if not id_ok(value.get('completion_id'),'engineering-completion'): e.append('completion_id_malformed')
    if not fp_ok(value.get('fingerprint')) or value.get('fingerprint')!=_fp_body(value): e.append('fingerprint_mismatch')
    if value.get('completion_status') not in COMPLETION_STATUSES or value.get('status')!=value.get('completion_status'): e.append('status_invalid')
    if value.get('deterministic') is not True or value.get('immutable') is not True: e.append('determinism_immutability_invalid')
    if value.get('authority_boundary')!=AUTHORITY_BOUNDARY: e.append('authority_boundary_invalid')
    if task_id and value.get('task_id')!=task_id: e.append('task_id_mismatch')
    if repository_identity is not None and value.get('repository_identity')!=repository_identity: e.append('repository_identity_mismatch')
    if proposal and (value.get('proposal_identity')!=_proposal_identity(proposal) or value.get('proposal_fingerprint')!=_proposal_fingerprint(proposal)): e.append('proposal_linkage_mismatch')
    if verification_result:
        vid=verification_result.get('verification_result_id') or verification_result.get('artifact_identity')
        vfp=verification_result.get('fingerprint') or verification_result.get('artifact_fingerprint')
        if value.get('verification_result_identity')!=vid or value.get('verification_result_fingerprint')!=vfp: e.append('verification_linkage_mismatch')
        if (verification_result.get('verification_status') or verification_result.get('validation_status')) not in SUCCESS_VERIFICATION_STATUSES: e.append('verification_not_passed')
    if value.get('completion_status')=='completed' and value.get('closure_eligibility') is not True: e.append('closure_eligibility_invalid')
    if value.get('completion_status')!='completed' and value.get('closure_eligibility') is True: e.append('closure_eligibility_invalid')
    if not isinstance(value.get('completion_summary'),str) or len(value.get('completion_summary'))>_MAX_SUMMARY: e.append('summary_unbounded')
    e += authority_errors(value)
    return result(e)
