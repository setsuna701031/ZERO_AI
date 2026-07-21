from __future__ import annotations

from typing import Any, Mapping, Sequence

from core.engineering.engineering_multifile_coding_workflow import canon, classify_role
from core.engineering.engineering_practical_task_runner import _ref

PLANNING_SCHEMA='zero.engineering.repair_planning_intake.v1'
HYPOTHESIS_SCHEMA='zero.engineering.root_cause_hypothesis_candidate.v1'
IMPACT_SCHEMA='zero.engineering.repair_impact_analysis.v1'
STRATEGY_SCHEMA='zero.engineering.repair_strategy_candidate.v1'
PATCH_SCHEMA='zero.engineering.patch_candidate.v1'
VALIDATION_SCHEMA='zero.engineering.patch_candidate_validation.v1'
REVIEW_SCHEMA='zero.engineering.patch_candidate_review.v1'
AUTHORITY={'may_modify_repository':False,'may_execute':False,'may_retry':False,'may_approve':False,'may_authorize':False,'may_complete':False}
STORE_FILES={'planning_intake':'repair/planning-intake.json','hypothesis':'repair/root-cause-hypothesis.json','impact':'repair/impact-analysis.json','strategy':'repair/strategy-candidate.json','patch':'repair/patch-candidate.json','validation':'repair/patch-validation.json','review':'repair/patch-review.json'}
ACCEPTED_REPAIR_REVIEWS={'accept_for_planning','confirmed'}
FORBIDDEN_PATCH_KEYS={'content','diff','replacement','old_text','new_text','command','argv','shell','operations','ordered_operations','authorization','execution'}

class RepairPlanningError(ValueError):
    def __init__(self,code): super().__init__(code); self.code=code

def build_repair_planning_intake(*,work_request:Mapping[str,Any],confirmed_specification:Mapping[str,Any],human_plan_confirmation:Mapping[str,Any],reproduction_result:Mapping[str,Any],test_failure_evidence:Mapping[str,Any],repair_proposal_candidate:Mapping[str,Any],human_repair_review:Mapping[str,Any],repository_identity:Mapping[str,Any],confirmed_scope:Sequence[str],iteration_reference:Mapping[str,Any],session_id:str)->dict[str,Any]:
    if not test_failure_evidence: raise RepairPlanningError('missing_failure_evidence')
    if not repair_proposal_candidate: raise RepairPlanningError('missing_repair_candidate')
    if not human_repair_review: raise RepairPlanningError('missing_human_repair_review')
    if human_repair_review.get('decision') not in ACCEPTED_REPAIR_REVIEWS: raise RepairPlanningError('repair_review_not_accepted')
    if human_repair_review.get('repair_candidate_reference')!=_ref(repair_proposal_candidate): raise RepairPlanningError('unresolved_repair_candidate')
    if repair_proposal_candidate.get('test_failure_evidence_reference')!=_ref(test_failure_evidence): raise RepairPlanningError('stale_repair_evidence')
    body={'schema':PLANNING_SCHEMA,'session_id':session_id,'work_request_reference':_ref(work_request),'confirmed_specification_reference':_ref(confirmed_specification),'human_plan_confirmation_reference':_ref(human_plan_confirmation),'reproduction_result_reference':_ref(reproduction_result),'test_failure_evidence_reference':_ref(test_failure_evidence),'repair_proposal_candidate_reference':_ref(repair_proposal_candidate),'human_repair_review_reference':_ref(human_repair_review),'repository_identity':dict(repository_identity),'confirmed_scope':list(confirmed_scope),'iteration_reference':dict(iteration_reference),'authority':AUTHORITY}
    return canon(body,'repair_planning_fingerprint','repair_planning_id','engineering-repair-planning-')

def build_root_cause_hypothesis(planning:Mapping[str,Any],failure_evidence:Mapping[str,Any],repair_candidate:Mapping[str,Any])->dict[str,Any]:
    suspected=repair_candidate.get('suspected_paths') or failure_evidence.get('suspected_related_paths') or []
    first=suspected[0] if suspected else {}; evidence=[]
    for item in suspected[:8]: evidence.append({'path':item.get('path'),'evidence_reasons':list(item.get('evidence_reasons') or []),'confidence_band':item.get('confidence_band','low')})
    bands=[x.get('confidence_band') for x in evidence]; confidence='high' if 'high' in bands else 'medium' if 'medium' in bands else 'low'
    body={'schema':HYPOTHESIS_SCHEMA,'session_id':planning.get('session_id'),'repair_planning_reference':_ref(planning),'failure_evidence_reference':_ref(failure_evidence),'suspected_component':first.get('path'),'suspected_symbols':[],'supporting_evidence':evidence,'contradicting_evidence':[],'alternative_hypotheses':['failure may originate in an unobserved dependency','test expectation may be stale'],'confidence_band':confidence,'limitations':['bounded failure evidence only','hypothesis is not root-cause confirmation'],'confirmed_root_cause':False,'authority':AUTHORITY}
    return canon(body,'hypothesis_fingerprint','hypothesis_id','engineering-root-cause-hypothesis-')

def build_repair_impact_analysis(planning:Mapping[str,Any],hypothesis:Mapping[str,Any],failure_evidence:Mapping[str,Any],repair_candidate:Mapping[str,Any],repository_analysis:Mapping[str,Any])->dict[str,Any]:
    scope=list(planning.get('confirmed_scope') or []); suspected=sorted({x.get('path') for x in repair_candidate.get('suspected_paths',[]) if x.get('path')}); direct=[p for p in suspected if p in scope]; possible=[p for p in suspected if p not in direct]
    relationship='requires_scope_expansion' if possible else 'within_confirmed_scope' if direct else 'unknown'
    tests=sorted({f.get('test_node') for f in failure_evidence.get('failed_tests',[]) if f.get('test_node')})
    body={'schema':IMPACT_SCHEMA,'session_id':planning.get('session_id'),'repair_planning_reference':_ref(planning),'root_cause_hypothesis_reference':_ref(hypothesis),'repository_analysis_reference':_ref(repository_analysis),'directly_affected_paths':direct,'possibly_affected_paths':possible,'affected_symbols':[],'dependent_modules':[],'existing_test_targets':tests,'additional_test_candidates':[],'configuration_impact':'unknown','documentation_impact':'unknown','compatibility_risks':['root cause remains unconfirmed'],'scope_relationship':relationship,'requires_human_scope_review':relationship=='requires_scope_expansion','authority':AUTHORITY}
    return canon(body,'impact_analysis_fingerprint','impact_analysis_id','engineering-repair-impact-')

def build_repair_strategy_candidate(planning:Mapping[str,Any],hypothesis:Mapping[str,Any],impact:Mapping[str,Any])->dict[str,Any]:
    paths=list(impact.get('directly_affected_paths') or [])
    body={'schema':STRATEGY_SCHEMA,'session_id':planning.get('session_id'),'repair_planning_reference':_ref(planning),'root_cause_hypothesis_reference':_ref(hypothesis),'impact_analysis_reference':_ref(impact),'repair_objective':'Address the observed failure through a separately human-defined patch while preserving confirmed scope.','strategy_summary':'Review suspected paths and define bounded changes only after Human Patch Review.','alternative_strategies':['revise the hypothesis after additional read-only evidence','return for human scope review'],'selected_strategy_rationale':'Uses only observed failure evidence and confirmed paths.','affected_paths':paths,'affected_symbols':list(impact.get('affected_symbols') or []),'test_strategy':{'required_test_targets':list(impact.get('existing_test_targets') or []),'maximum_targets':8,'timeout_seconds':120,'bounded':True},'rollback_considerations':['no patch is executable at this stage'],'risk_summary':'root cause unconfirmed; patch definition requires human review','uncertainties':['exact code change is undefined'],'blocking_questions':['Human scope review required'] if impact.get('requires_human_scope_review') else [],'authority':AUTHORITY}
    return canon(body,'repair_strategy_fingerprint','repair_strategy_id','engineering-repair-strategy-')

def _dependency_order(items:Sequence[Mapping[str,Any]])->list[str]:
    ids={x.get('patch_item_id') for x in items}; temp=set(); done=set(); order=[]
    def visit(item_id):
        if item_id in temp: raise RepairPlanningError('dependency_cycle')
        if item_id in done: return
        if item_id not in ids: raise RepairPlanningError('unknown_dependency')
        temp.add(item_id); item=next(x for x in items if x.get('patch_item_id')==item_id)
        for dep in item.get('depends_on') or []: visit(dep)
        temp.remove(item_id); done.add(item_id); order.append(item_id)
    for item_id in sorted(ids): visit(item_id)
    return order

def build_patch_candidate(planning:Mapping[str,Any],strategy:Mapping[str,Any],impact:Mapping[str,Any],*,acceptance_criteria:Sequence[str])->dict[str,Any]:
    if impact.get('requires_human_scope_review'): raise RepairPlanningError('scope_expansion_required')
    paths=sorted(set(strategy.get('affected_paths') or [])); items=[]; criteria=list(acceptance_criteria or [])
    for index,path in enumerate(paths,1): items.append({'patch_item_id':f'patch-{index:04d}','path':path,'file_role':classify_role(path),'change_kind':'modify','change_intent':'human-defined bounded repair for the reviewed hypothesis','related_symbols':[],'depends_on':[],'related_acceptance_criteria':criteria[:1],'repository_evidence':[{'path':path,'basis':'reviewed repair impact'}],'expected_test_impact':'covered by bounded confirmed tests','risk_level':'medium','operation_definition_status':'requires_human_definition'})
    order=_dependency_order(items)
    body={'schema':PATCH_SCHEMA,'session_id':planning.get('session_id'),'repair_planning_reference':_ref(planning),'repair_strategy_reference':_ref(strategy),'impact_analysis_reference':_ref(impact),'repository_identity':planning.get('repository_identity'),'confirmed_scope':list(planning.get('confirmed_scope') or []),'ordered_patch_items':items,'acceptance_criterion_mappings':[{'acceptance_criterion':c,'patch_item_ids':[x['patch_item_id'] for x in items]} for c in criteria],'dependency_order':order,'test_plan':strategy.get('test_strategy'),'risk_summary':strategy.get('risk_summary'),'uncertainties':list(strategy.get('uncertainties') or []),'blocking_questions':list(strategy.get('blocking_questions') or []),'operation_definition_status':'requires_human_definition' if items else 'not_applicable','authority':AUTHORITY}
    return canon(body,'patch_candidate_fingerprint','patch_candidate_id','engineering-patch-candidate-')

def validate_patch_candidate(patch:Mapping[str,Any],*,planning:Mapping[str,Any]|None=None,strategy:Mapping[str,Any]|None=None,impact:Mapping[str,Any]|None=None,failure_evidence:Mapping[str,Any]|None=None,repair_candidate:Mapping[str,Any]|None=None,human_repair_review:Mapping[str,Any]|None=None,repository_analysis:Mapping[str,Any]|None=None,repository_identity:Mapping[str,Any]|None=None,session_id:str|None=None,iteration_reference:Mapping[str,Any]|None=None)->dict[str,Any]:
    errors=[]; material={k:v for k,v in patch.items() if k not in {'patch_candidate_fingerprint','patch_candidate_id'}}; expected=canon(material,'patch_candidate_fingerprint','patch_candidate_id','engineering-patch-candidate-')
    if patch.get('schema')!=PATCH_SCHEMA or expected!=patch: errors.append('stale_repair_evidence')
    if not failure_evidence: errors.append('missing_failure_evidence')
    if not repair_candidate: errors.append('missing_repair_candidate')
    if not human_repair_review: errors.append('missing_human_repair_review')
    elif human_repair_review.get('decision') not in ACCEPTED_REPAIR_REVIEWS: errors.append('repair_review_not_accepted')
    elif planning and planning.get('human_repair_review_reference')!=_ref(human_repair_review): errors.append('stale_repair_evidence')
    if planning and planning.get('test_failure_evidence_reference')!=_ref(failure_evidence or {}): errors.append('unresolved_failure_evidence')
    if planning and planning.get('repair_proposal_candidate_reference')!=_ref(repair_candidate or {}): errors.append('unresolved_repair_candidate')
    if repository_identity is not None and dict(patch.get('repository_identity') or {})!=dict(repository_identity): errors.append('wrong_repository_identity')
    if session_id and patch.get('session_id')!=session_id: errors.append('session_mismatch')
    if iteration_reference is not None and planning and planning.get('iteration_reference')!=dict(iteration_reference): errors.append('iteration_mismatch')
    if strategy and patch.get('repair_strategy_reference')!=_ref(strategy): errors.append('stale_repair_evidence')
    if impact and impact.get('requires_human_scope_review'): errors.append('scope_expansion_required')
    scope=patch.get('confirmed_scope') or []; items=patch.get('ordered_patch_items') or []; paths=[x.get('path') for x in items]
    if any(not any(p==s or str(p).startswith(str(s).rstrip('/')+'/') for s in scope) for p in paths): errors.append('silent_scope_expansion')
    observed={x.get('path') for x in (repository_analysis or {}).get('files',[]) if x.get('path')}
    if repository_analysis and any(p not in observed for p in paths): errors.append('unknown_patch_path')
    if any(not x.get('related_acceptance_criteria') for x in items): errors.append('missing_acceptance_mapping')
    try:
        if _dependency_order(items)!=patch.get('dependency_order'): errors.append('dependency_cycle')
    except RepairPlanningError as exc: errors.append(exc.code)
    test=patch.get('test_plan') or {}; targets=test.get('required_test_targets') or []
    if not test.get('bounded') or len(targets)>8 or int(test.get('timeout_seconds') or 0)>120: errors.append('unbounded_test_plan')
    if any(x.get('operation_definition_status') not in {'requires_human_definition','not_applicable'} or FORBIDDEN_PATCH_KEYS.intersection(x) for x in items): errors.append('executable_operation_prohibited')
    if any(patch.get('authority',{}).get(k) for k in AUTHORITY) or FORBIDDEN_PATCH_KEYS.intersection(patch): errors.append('authority_payload_rejection')
    result={'schema':VALIDATION_SCHEMA,'patch_candidate_reference':_ref(patch),'valid':not errors,'reason_codes':sorted(set(errors)),'validation_status':'valid' if not errors else 'invalid','authority':AUTHORITY}
    return canon(result,'patch_validation_fingerprint','patch_validation_id','engineering-patch-validation-')

def review_patch_candidate(patch:Mapping[str,Any],validation:Mapping[str,Any],review:Mapping[str,Any])->dict[str,Any]:
    if not review.get('human_actor'): raise RepairPlanningError('human_actor_required')
    if review.get('patch_candidate_reference')!=_ref(patch): raise RepairPlanningError('stale_patch_candidate')
    decision=review.get('decision')
    if decision not in {'confirmed','rejected','requires_revision'}: raise RepairPlanningError('invalid_patch_review_decision')
    if decision=='confirmed' and validation.get('validation_status')!='valid': raise RepairPlanningError('invalid_patch_candidate')
    body={'schema':REVIEW_SCHEMA,'patch_candidate_reference':_ref(patch),'patch_validation_reference':_ref(validation),'human_actor':review['human_actor'],'decision':decision,'confirmed_paths':list(review.get('confirmed_paths') or []),'confirmed_patch_item_ids':list(review.get('confirmed_patch_item_ids') or []),'confirmed_test_targets':list(review.get('confirmed_test_targets') or []),'risk_acknowledgements':list(review.get('risk_acknowledgements') or []),'scope_acknowledgement':bool(review.get('scope_acknowledgement')),'notes':review.get('notes',''),'not_approval':True,'not_authorization':True,'not_execution_permission':True,'authority':AUTHORITY}
    return canon(body,'patch_review_fingerprint','patch_review_id','engineering-patch-review-')

def revise_patch_candidate(patch:Mapping[str,Any],revision:Mapping[str,Any])->dict[str,Any]:
    allowed={'affected_paths','acceptance_criteria','blocking_questions','revision_reason'}
    if set(revision)-allowed: raise RepairPlanningError('executable_operation_prohibited')
    body={k:v for k,v in patch.items() if k not in {'patch_candidate_fingerprint','patch_candidate_id'}}; body['previous_patch_reference']=_ref(patch); body['revision_reason']=revision.get('revision_reason'); body['blocking_questions']=list(revision.get('blocking_questions') or body.get('blocking_questions') or [])
    return canon(body,'patch_candidate_fingerprint','patch_candidate_id','engineering-patch-candidate-')

def inspect_repair_planning_state(bundle:Mapping[str,Any])->dict[str,Any]:
    get=lambda key:bundle.get(STORE_FILES[key]) or {}
    return {'human_repair_review_status':(bundle.get('feedback/repair-review.json') or {}).get('decision','missing'),'root_cause_hypothesis_status':'created' if get('hypothesis') else 'missing','impact_analysis_status':get('impact').get('scope_relationship','missing'),'repair_strategy_status':'created' if get('strategy') else 'missing','patch_candidate_status':'created' if get('patch') else 'missing','patch_validation_status':get('validation').get('validation_status','not_started'),'scope_expansion_status':'required' if get('impact').get('requires_human_scope_review') else 'not_required','human_patch_review_status':get('review').get('decision','not_started'),'next_governed_action':resume_repair_planning_state(bundle)['decision']}

def resume_repair_planning_state(bundle:Mapping[str,Any])->dict[str,Any]:
    if not bundle.get('feedback/repair-review.json'): decision='requires_human_repair_review'
    elif not bundle.get(STORE_FILES['planning_intake']): decision='requires_repair_planning_intake'
    elif not bundle.get(STORE_FILES['hypothesis']): decision='requires_root_cause_hypothesis'
    elif not bundle.get(STORE_FILES['impact']): decision='requires_impact_analysis'
    elif (bundle.get(STORE_FILES['impact']) or {}).get('requires_human_scope_review'): decision='requires_human_scope_review'
    elif not bundle.get(STORE_FILES['strategy']): decision='requires_repair_strategy'
    elif not bundle.get(STORE_FILES['patch']): decision='requires_patch_candidate'
    elif not bundle.get(STORE_FILES['validation']): decision='requires_patch_validation'
    elif not bundle.get(STORE_FILES['review']): decision='requires_human_patch_review'
    else: decision='human_patch_review_recorded'
    return {'schema':'zero.engineering.repair_planning_resume.v1','decision':decision,'will_confirm':False,'will_modify_repository':False,'will_create_change_package':False,'will_approve':False,'will_authorize':False,'will_execute':False,'will_retry':False,'will_complete':False}
