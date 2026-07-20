from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_bootstrap_request import SCHEMA as REQUEST_SCHEMA, AUTHORITY_BOUNDARY as REQUEST_BOUNDARY
from core.engineering.engineering_bootstrap_request_validation import validate_engineering_bootstrap_request
from core.engineering.repository_analysis_report import validate_repository_analysis_report
from core.engineering.engineering_repair_candidate import build_engineering_repair_candidate
from core.engineering.engineering_repair_candidate_validation import validate_engineering_repair_candidate
from core.engineering.engineering_repair_plan import build_engineering_repair_plan, EXPECTATION_TYPES
from core.engineering.engineering_repair_plan_validation import validate_engineering_repair_plan
from core.engineering.engineering_change_proposal import assemble_change_proposal
from core.engineering.engineering_completion_foundation import build_proposal_linkage, validate_proposal_linkage
from core.engineering.engineering_task_orchestration import create_task, admit_task, attach_analysis, attach_candidate_selection, attach_plan, attach_proposal, inspect_task, OrchestrationError
from core.engineering.engineering_task_orchestration_validation import canonical_request
from core.engineering.engineering_planning_common import seal, short_text, subset, no_overlap
from core.engineering.engineering_mutation_transaction_common import fingerprint

RESULT_SCHEMA='zero.engineering.bootstrap_result.v1'
RESULT_STATUSES=('proposal_ready','blocked','failed','invalid','insufficient_evidence')
RESULT_AUTHORITY_BOUNDARY={'approval':'not_granted','authorization':'not_granted','token':'not_granted','execution':'not_granted','verification':'not_granted','mutation':'not_granted','git':'not_granted','shell':'not_granted','network':'not_granted'}

def _analysis_id(a): return a.get('repository_analysis_report_id') or a.get('artifact_identity')
def _analysis_fp(a): return a.get('fingerprint') or a.get('artifact_fingerprint')
def _ev(analysis):
    ids=analysis.get('evidence_index') or []
    return [{'evidence_id':str(x),'evidence_type':'repository_analysis_evidence','source_artifact_identity':_analysis_id(analysis),'source_fingerprint':_analysis_fp(analysis),'bounded_summary':'Canonical repository analysis evidence reference.'} for x in sorted(ids)]
def _summary_paths(analysis, request):
    repo=analysis.get('repository_summary') or {}
    paths=repo.get('analyzed_paths') or repo.get('normalized_scope') or request.get('target_scope')
    return sorted(p for p in paths if isinstance(p,str))
def build_engineering_bootstrap_result(*, request:Mapping[str,Any], repository_identity:Any, status:str, blocked_reason_codes:Any=(), summary:str='Engineering bootstrap recorded.', analysis:Mapping[str,Any]|None=None, candidate:Mapping[str,Any]|None=None, repair_plan:Mapping[str,Any]|None=None, proposal:Mapping[str,Any]|None=None, proposal_linkage:Mapping[str,Any]|None=None)->dict[str,Any]:
    def ident(a,k): return (a or {}).get(k)
    body={'schema':RESULT_SCHEMA,'bootstrap_request_identity':request.get('bootstrap_request_id'),'bootstrap_request_fingerprint':request.get('fingerprint'),'repository_identity':repository_identity,'analysis_identity':_analysis_id(analysis or {}),'analysis_fingerprint':_analysis_fp(analysis or {}),'candidate_identity':ident(candidate,'candidate_id'),'candidate_fingerprint':ident(candidate,'fingerprint'),'repair_plan_identity':ident(repair_plan,'repair_plan_id'),'repair_plan_fingerprint':ident(repair_plan,'fingerprint'),'proposal_identity':ident(proposal,'proposal_id'),'proposal_fingerprint':ident(proposal,'fingerprint'),'proposal_linkage_identity':ident(proposal_linkage,'proposal_linkage_id'),'proposal_linkage_fingerprint':ident(proposal_linkage,'fingerprint'),'bootstrap_status':status,'status':status,'blocked_reason_codes':sorted(dict.fromkeys(str(x) for x in blocked_reason_codes)),'summary':short_text(summary,640),'deterministic':True,'immutable':True,'authority_boundary':RESULT_AUTHORITY_BOUNDARY}
    return seal(body,'bootstrap_result_id','engineering-bootstrap-result')

def validate_engineering_bootstrap_result(value:Any)->Any:
    from core.engineering.engineering_planning_common import ValidationResult, fp_ok, id_ok, result, authority_errors
    e=[]
    if not isinstance(value,Mapping): return ValidationResult(False,('artifact_not_mapping',))
    req={'schema','bootstrap_result_id','fingerprint','bootstrap_request_identity','bootstrap_request_fingerprint','repository_identity','analysis_identity','analysis_fingerprint','candidate_identity','candidate_fingerprint','repair_plan_identity','repair_plan_fingerprint','proposal_identity','proposal_fingerprint','proposal_linkage_identity','proposal_linkage_fingerprint','bootstrap_status','status','blocked_reason_codes','summary','deterministic','immutable','authority_boundary'}
    e += [f'missing:{k}' for k in sorted(req-set(value))]
    if value.get('schema')!=RESULT_SCHEMA: e.append('schema_mismatch')
    if value.get('bootstrap_status') not in RESULT_STATUSES or value.get('status')!=value.get('bootstrap_status'): e.append('status_invalid')
    if not id_ok(value.get('bootstrap_result_id'),'engineering-bootstrap-result'): e.append('bootstrap_result_id_malformed')
    if not fp_ok(value.get('fingerprint')) or value.get('fingerprint')!=fingerprint({k:v for k,v in value.items() if k!='fingerprint'}): e.append('fingerprint_mismatch')
    if value.get('deterministic') is not True or value.get('immutable') is not True: e.append('determinism_immutability_invalid')
    if value.get('authority_boundary')!=RESULT_AUTHORITY_BOUNDARY: e.append('authority_boundary_invalid')
    e += authority_errors(value)
    return result(e)

def bootstrap_engineering_task(*, repo_root:Any, bootstrap_request:Mapping[str,Any], repository_analysis:Mapping[str,Any])->dict[str,Any]:
    rv=validate_engineering_bootstrap_request(bootstrap_request)
    if not rv.valid: return build_engineering_bootstrap_result(request=bootstrap_request,repository_identity=bootstrap_request.get('repository_identity'),status='invalid',blocked_reason_codes=rv.errors,summary='Bootstrap request failed validation.')
    av=validate_repository_analysis_report(repository_analysis)
    if not av.valid or repository_analysis.get('status')!='reported': return build_engineering_bootstrap_result(request=bootstrap_request,repository_identity=bootstrap_request.get('repository_identity'),status='insufficient_evidence',blocked_reason_codes=av.errors or ('analysis_not_reported',),analysis=repository_analysis,summary='Canonical repository analysis is insufficient for planning.')
    ev=_ev(repository_analysis); paths=_summary_paths(repository_analysis, bootstrap_request)
    if not ev:
        return build_engineering_bootstrap_result(request=bootstrap_request,repository_identity=bootstrap_request.get('repository_identity'),status='insufficient_evidence',blocked_reason_codes=('insufficient_evidence',),analysis=repository_analysis,summary='Analysis evidence cannot safely select a candidate.')
    if not paths or not subset(paths, bootstrap_request['target_scope']) or not no_overlap(paths, bootstrap_request['prohibited_scope']):
        return build_engineering_bootstrap_result(request=bootstrap_request,repository_identity=bootstrap_request.get('repository_identity'),status='blocked',blocked_reason_codes=('out_of_scope_evidence',),analysis=repository_analysis,summary='Analysis evidence cannot safely select a candidate.')
    task_req=canonical_request({'repository_identity':bootstrap_request['repository_identity'],'requested_outcome':bootstrap_request['requested_outcome'],'bounded_target_scope':bootstrap_request['target_scope'],'prohibited_scope':bootstrap_request['prohibited_scope'],'requested_verification_expectations':bootstrap_request['verification_expectations'],'bootstrap_request_identity':bootstrap_request['bootstrap_request_id'],'bootstrap_request_fingerprint':bootstrap_request['fingerprint']})
    state=create_task(repo_root, task_req); state=admit_task(repo_root,state['task_id']); state=attach_analysis(repo_root,state['task_id'],repository_analysis)
    candidate=dict(build_engineering_repair_candidate(task_id=state['task_id'],repository_identity=bootstrap_request['repository_identity'],analysis_identity=_analysis_id(repository_analysis),analysis_fingerprint=_analysis_fp(repository_analysis),requested_outcome=bootstrap_request['requested_outcome'],defect_classification='unknown_bounded_defect',defect_summary='Bounded deterministic candidate selected from canonical repository analysis.',evidence_references=ev,target_scope=paths,prohibited_scope=bootstrap_request['prohibited_scope'],affected_components=paths,estimated_change_kind=bootstrap_request['allowed_change_kinds'][0],risk_level='medium',confidence=0.8,selection_status='selected'))
    cv=validate_engineering_repair_candidate(candidate, task_id=state['task_id'], repository_identity=bootstrap_request['repository_identity'], analysis_identity=_analysis_id(repository_analysis), analysis_fingerprint=_analysis_fp(repository_analysis), request_scope=bootstrap_request['target_scope'])
    if not cv.valid: return build_engineering_bootstrap_result(request=bootstrap_request,repository_identity=bootstrap_request['repository_identity'],status='blocked',blocked_reason_codes=cv.errors,analysis=repository_analysis,candidate=candidate,summary='Candidate validation blocked planning.')
    state=attach_candidate_selection(repo_root,state['task_id'],candidate)
    exp_type=next((x for x in bootstrap_request['verification_expectations'] if x in EXPECTATION_TYPES),'file_exists')
    expectations=[{'expectation_id':'bootstrap-verify-'+fingerprint({'path':p,'type':exp_type})[:16],'expectation_type':exp_type,'required':True,'expected_status':'satisfied','description':'Bounded post-plan verification expectation.','target_path':p} for p in paths]
    ops=[{'operation_type':'replace_file' if candidate['estimated_change_kind'] in ('replace_file','mixed') else candidate['estimated_change_kind'],'target_path':p,'rationale':'Operation derived from selected bounded candidate scope.','expected_postcondition':'Target remains governed by downstream mutation authorization.','verification_expectation_ids':[expectations[i]['expectation_id']]} for i,p in enumerate(paths)]
    plan=dict(build_engineering_repair_plan(candidate=candidate, ordered_operations=ops, verification_expectations=expectations, prohibited_target_paths=bootstrap_request['prohibited_scope'], constraints=bootstrap_request['constraints'], assumptions=bootstrap_request['assumptions']))
    pv=validate_engineering_repair_plan(plan, candidate=candidate, task_id=state['task_id'], repository_identity=bootstrap_request['repository_identity'], analysis_identity=_analysis_id(repository_analysis), request_scope=bootstrap_request['target_scope'])
    if not pv.valid: return build_engineering_bootstrap_result(request=bootstrap_request,repository_identity=bootstrap_request['repository_identity'],status='blocked',blocked_reason_codes=pv.errors,analysis=repository_analysis,candidate=candidate,repair_plan=plan,summary='Repair plan validation blocked proposal.')
    state=attach_plan(repo_root,state['task_id'],plan)
    prop=assemble_change_proposal({'intent':{'requested_outcome':bootstrap_request['requested_outcome']},'workspace_evidence':{'workspace_id':'engineering-bootstrap-read-only'},'scope_policy':{'maximum_affected_files':len(paths),'maximum_total_proposed_content_bytes':0},'operations':[],'contents':[],'authority_constraints':['approval_not_granted','authorization_not_granted','mutation_not_performed'],'validation_requirements':bootstrap_request['verification_expectations']})
    link=build_proposal_linkage(task_id=state['task_id'],repository_identity=bootstrap_request['repository_identity'],analysis=repository_analysis,candidate=candidate,repair_plan=plan,proposal=prop)
    lv=validate_proposal_linkage(link,task_id=state['task_id'],repository_identity=bootstrap_request['repository_identity'],analysis=repository_analysis,candidate=candidate,repair_plan=plan,proposal=prop)
    if not lv.valid: return build_engineering_bootstrap_result(request=bootstrap_request,repository_identity=bootstrap_request['repository_identity'],status='blocked',blocked_reason_codes=lv.errors,analysis=repository_analysis,candidate=candidate,repair_plan=plan,proposal=prop,proposal_linkage=link,summary='Proposal linkage validation blocked attach.')
    state=attach_proposal(repo_root,state['task_id'],{'proposal':prop,'proposal_linkage':link})
    return build_engineering_bootstrap_result(request=bootstrap_request,repository_identity=bootstrap_request['repository_identity'],status='proposal_ready',analysis=repository_analysis,candidate=candidate,repair_plan=plan,proposal=prop,proposal_linkage=link,summary='Bootstrap created canonical proposal package and stopped awaiting approval.')
