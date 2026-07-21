from __future__ import annotations
from pathlib import Path
from typing import Any, Mapping, Sequence
from core.engineering.engineering_runtime_orchestrator_common import fingerprint
from core.engineering.engineering_approval_execution_activation import ActivationError
from core.engineering.engineering_practical_task_runner import build_governed_change_package, run_bounded_test_operation, bounded_test_policy, _ref, safe_path

PLAN_SCHEMA='zero.engineering.multifile_change_plan_candidate.v1'
CONFIRM_SCHEMA='zero.engineering.multifile_change_plan_confirmation.v1'
TEST_SET_SCHEMA='zero.engineering.bounded_test_set_result.v1'
REVIEW_SCHEMA='zero.engineering.repair_candidate_review.v1'
ITERATION_SCHEMA='zero.engineering.iteration_index.v1'
AUTHORITY={'may_approve':False,'may_authorize':False,'may_execute':False,'may_complete':False}
REPAIR_AUTHORITY={**AUTHORITY,'may_retry':False}
ROLES={'production','test','documentation','configuration','fixture','unknown'}
KINDS={'create','modify','rename','append','remove_exact_section','unknown'}
STATUSES={'draft','requires_clarification','ready_for_confirmation','confirmed','rejected','superseded','blocked','invalid'}
OPSTAT={'deterministic','requires_exact_content','requires_human_definition','unsupported'}
STOP={'first_failure','continue'}
ITERATION_POLICY={'maximum_recorded_iterations':8,'automatic_iterations':0}

def canon(body:Mapping[str,Any], fp_key:str, id_key:str, prefix:str)->dict[str,Any]:
    b=dict(body); fp=fingerprint(b); b[fp_key]=fp; b[id_key]=prefix+fp[:24]; return b

def classify_role(path:str)->str:
    p=path.replace('\\','/')
    if p.startswith('tests/') or '/test_' in p or p.endswith('_test.py'): return 'test'
    if p.endswith(('.md','.rst')): return 'documentation'
    if p.endswith(('.json','.toml','.yaml','.yml','.ini')): return 'configuration'
    if 'fixture' in p: return 'fixture'
    return 'production' if p.endswith('.py') else 'unknown'

def _scope(spec, work): return list(spec.get('confirmed_scope') or spec.get('confirmed_paths') or work.get('requested_scope') or [])
def _acs(spec, explicit): return list(explicit or spec.get('acceptance_criteria') or spec.get('confirmed_acceptance_criteria') or ['bounded_acceptance'])
def _in_scope(path, scope): return any(path==s or path.startswith(str(s).rstrip('/')+'/') for s in scope)
def _evidence_paths(analysis):
    vals=set()
    def walk(x):
        if isinstance(x, Mapping):
            for k,v in x.items():
                if k in {'path','file','target_path'} and isinstance(v,str): vals.add(v)
                walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(analysis); return vals

def topo(changes:Sequence[Mapping[str,Any]])->list[str]:
    ids=[c['change_id'] for c in changes]; by={c['change_id']:list(c.get('depends_on') or []) for c in changes}
    out=[]; temp=set(); perm=set()
    def visit(n):
        if n in temp: raise ActivationError('cyclic_dependency')
        if n in perm: return
        if n not in by: raise ActivationError('unknown_dependency')
        temp.add(n)
        for d in sorted(by[n]):
            if d==n: raise ActivationError('self_dependency')
            visit(d)
        temp.remove(n); perm.add(n); out.append(n)
    for n in ids: visit(n)
    return out

def build_multifile_change_plan_candidate(*, confirmed_specification:Mapping[str,Any], work_request:Mapping[str,Any], repository_analysis:Mapping[str,Any], repository_identity:Mapping[str,Any]|None=None, acceptance_criteria:Sequence[str]|None=None, human_operation_hints:Mapping[str,Any]|None=None, previous_plan_reference:Mapping[str,Any]|None=None, revision_reason:str|None=None, human_revision_input:Mapping[str,Any]|None=None, session_id:str|None=None)->dict[str,Any]:
    if not confirmed_specification: raise ActivationError('confirmed_specification_required')
    if not work_request: raise ActivationError('work_request_required')
    if confirmed_specification.get('schema')=='zero.engineering.work_specification_candidate.v1' or confirmed_specification.get('confirmation_status') not in {None,'confirmed'}: raise ActivationError('unconfirmed_specification')
    hints=human_operation_hints or {}; scope=_scope(confirmed_specification, work_request); acs=_acs(confirmed_specification, acceptance_criteria); evidence=_evidence_paths(repository_analysis)|set(scope)
    paths=list(hints.get('paths') or scope); seen=[]
    for p in paths:
        p=str(p).replace('\\','/');
        if p not in seen: seen.append(p)
    changes=[]
    for i,p in enumerate(sorted(seen, key=lambda x:(classify_role(x)=='test', x))):
        exists=p in evidence or Path(p).exists(); kind=(hints.get('change_kinds') or {}).get(p) or ('modify' if exists else 'create')
        status=(hints.get('operation_definition_status') or {}).get(p) or ('requires_human_definition' if kind in {'modify','unknown'} else 'requires_exact_content')
        cid=(hints.get('change_ids') or {}).get(p) or f'change-{i+1:04d}'
        changes.append({'change_id':cid,'path':p,'file_role':classify_role(p),'change_kind':kind,'change_intent':(hints.get('intents') or {}).get(p,'bounded implementation/test update for confirmed acceptance criteria'),'repository_evidence':[{'path':p,'evidence':'observed_or_confirmed_scope' if exists or _in_scope(p,scope) else 'missing'}],'related_symbols':(hints.get('symbols') or {}).get(p,[]),'related_acceptance_criteria':list((hints.get('acceptance_map') or {}).get(p,acs[:1])),'depends_on':list((hints.get('depends_on') or {}).get(cid,[])),'risk_level':(hints.get('risk_levels') or {}).get(p,'medium'),'operation_feasibility':'candidate_only','operation_definition_status':status,'expected_test_impact':'direct' if classify_role(p)=='test' else 'covered_by_focused_tests'})
    
    status='ready_for_confirmation' if not hints.get('blocking_questions') else 'requires_clarification'
    try:
        order=topo(changes) if changes else []
    except ActivationError:
        order=[]; status='invalid'
    tests=list(hints.get('test_targets') or sorted([p for p in seen if classify_role(p)=='test'])[:3])
    strategy={'required_test_targets':tests,'optional_test_targets':list(hints.get('optional_test_targets') or []),'prohibited_full_suite':True,'test_root_validation':'tests_only','maximum_targets':int(hints.get('maximum_targets',3)),'timeout_per_target':int(hints.get('timeout_per_target',120)),'execution_order':tests,'stop_policy':hints.get('stop_policy','first_failure'),'expected_coverage':'direct focused tests for mapped acceptance criteria','test_selection_evidence':[{'target':t,'evidence':'test file in confirmed scope or human hint'} for t in tests]}
    return canon({'schema':PLAN_SCHEMA,'governance_linkage_version':'v4.2','session_id':session_id,'confirmed_specification_reference':_ref(confirmed_specification),'work_request_reference':_ref(work_request),'repository_analysis_reference':_ref(repository_analysis),'repository_identity':dict(repository_identity or work_request.get('repository_identity') or {}),'plan_status':status,'intent':confirmed_specification.get('intent') or work_request.get('request_statement','bounded multifile change'),'ordered_file_changes':changes,'test_strategy':strategy,'acceptance_criterion_mappings':[{'acceptance_criterion':a,'change_ids':[c['change_id'] for c in changes if a in c.get('related_acceptance_criteria',[])]} for a in acs],'dependency_order':order,'risk_summary':hints.get('risk_summary','bounded multifile plan requires human confirmation and exact operations'),'uncertainties':list(hints.get('uncertainties') or []),'blocking_questions':list(hints.get('blocking_questions') or []),'prohibited_assumptions':['no executable operation is inferred from natural language','no approval authorization execution or completion authority'],'previous_plan_reference':previous_plan_reference,'revision_reason':revision_reason,'human_revision_input':human_revision_input,'authority':AUTHORITY},'plan_candidate_fingerprint','plan_candidate_id','engineering-multifile-plan-')

def validate_multifile_change_plan_candidate(plan:Mapping[str,Any], *, confirmed_specification:Mapping[str,Any]|None=None, work_request:Mapping[str,Any]|None=None, repository_root:str|Path='.', repository_analysis:Mapping[str,Any]|None=None, session_id:str|None=None)->dict[str,Any]:
    errors=[]
    if plan.get('schema')!=PLAN_SCHEMA: errors.append('schema_invalid')
    exp=canon({k:v for k,v in plan.items() if k not in {'plan_candidate_fingerprint','plan_candidate_id'}},'plan_candidate_fingerprint','plan_candidate_id','engineering-multifile-plan-')
    if exp.get('plan_candidate_fingerprint')!=plan.get('plan_candidate_fingerprint'): errors.append('fingerprint_mismatch')
    if not (confirmed_specification or plan.get('confirmed_specification_reference')): errors.append('missing_confirmed_specification')
    if not (work_request or plan.get('work_request_reference')): errors.append('missing_work_request')
    if not plan.get('repository_identity'): errors.append('unknown_repository_root')
    def check_ref(name, artifact, wrong_code):
        ref=plan.get(name) or {}
        ids={artifact.get(k) for k in artifact or {} if k.endswith('_id')}
        fps={artifact.get(k) for k in artifact or {} if k.endswith('fingerprint') or k=='fingerprint'}
        ref_ids={ref.get('artifact_identity')} if 'artifact_identity' in ref else {v for k,v in ref.items() if k.endswith('_id')}
        ref_fps={ref.get('artifact_fingerprint')} if 'artifact_fingerprint' in ref else {v for k,v in ref.items() if k.endswith('fingerprint') or k=='fingerprint'}
        if artifact and (not ids.intersection(ref_ids) or not fps.intersection(ref_fps)): errors.append(wrong_code)
    check_ref('confirmed_specification_reference',confirmed_specification,'wrong_specification_reference')
    check_ref('work_request_reference',work_request,'wrong_work_request_fingerprint')
    check_ref('repository_analysis_reference',repository_analysis,'wrong_repository_analysis_reference')
    if work_request and str(work_request.get('work_request_id','')).startswith('engineering-work-request-'):
        expected=fingerprint({k:v for k,v in work_request.items() if k not in {'work_request_fingerprint','work_request_id'}})
        if expected!=work_request.get('work_request_fingerprint'): errors.append('wrong_work_request_fingerprint')
    if confirmed_specification and confirmed_specification.get('confirmation_status') not in {None,'confirmed'}: errors.append('unconfirmed_specification')
    if work_request and dict(plan.get('repository_identity') or {})!=dict(work_request.get('repository_identity') or {}): errors.append('wrong_repository_identity')
    if confirmed_specification and work_request and sorted(_scope(confirmed_specification,{}))!=sorted(work_request.get('requested_scope') or []): errors.append('scope_mismatch')
    if session_id and plan.get('session_id') not in {None,session_id}: errors.append('plan_created_from_different_session')
    if plan.get('governance_linkage_version')=='v4.2' and work_request and confirmed_specification:
        source=work_request.get('source_actor_reference') or {}; spec_ref=source.get('specification_decision_reference') or {}
        if confirmed_specification.get('confirmation_id') and spec_ref.get('artifact_identity')!=confirmed_specification.get('confirmation_id'): errors.append('work_request_created_before_human_confirmation')
        elif confirmed_specification.get('confirmation_id') and spec_ref.get('artifact_fingerprint')!=confirmed_specification.get('confirmation_fingerprint'): errors.append('stale_work_request')
        if confirmed_specification.get('confirmation_id') and not source.get('natural_language_lineage'): errors.append('missing_intake_reference')
    scope=_scope(confirmed_specification or {}, work_request or {}) or [c.get('path') for c in plan.get('ordered_file_changes',[])]
    evidence=_evidence_paths(repository_analysis or {})|set(scope); ids=[]; paths=[]
    try:
        for c in plan.get('ordered_file_changes') or []:
            ids.append(c.get('change_id')); paths.append(c.get('path'))
            safe_path(repository_root,c.get('path',''))
            if c.get('file_role') not in ROLES: errors.append('invalid_file_role')
            if c.get('change_kind') not in KINDS: errors.append('invalid_change_kind')
            if c.get('operation_definition_status') not in OPSTAT: errors.append('invalid_operation_definition_status')
            if not c.get('related_acceptance_criteria'): errors.append('file_change_without_acceptance_mapping')
            if not _in_scope(c.get('path',''), scope): errors.append('unapproved_scope_expansion')
            if c.get('change_kind')!='create' and c.get('path') not in evidence: errors.append('evidence_free_existing_path')
        if len(paths)!=len(set(paths)): errors.append('duplicate_path_conflict')
        if topo(plan.get('ordered_file_changes') or [])!=plan.get('dependency_order'): errors.append('dependency_order_mismatch')
    except ActivationError as e: errors.append(e.code)
    ts=plan.get('test_strategy') or {}; targets=ts.get('required_test_targets') or []
    if not ts.get('prohibited_full_suite'): errors.append('full_suite_strategy')
    if len(targets)!=len(set(targets)): errors.append('duplicate_test_target')
    if len(targets)>int(ts.get('maximum_targets',3)): errors.append('maximum_targets_exceeded')
    for t in targets:
        if not t or not str(t).split('::')[0].startswith('tests/'): errors.append('test_target_outside_allowed_roots')
    if any(plan.get('authority',{}).get(k) for k in AUTHORITY): errors.append('candidate_with_execution_authority')
    return {'valid':not errors,'errors':sorted(set(errors)),'plan_validation_status':'valid' if not errors else 'invalid'}

def confirm_multifile_change_plan(plan, confirmation):
    if not confirmation.get('human_actor'): raise ActivationError('human_actor_required')
    dec=confirmation.get('decision')
    paths=[c['path'] for c in plan.get('ordered_file_changes',[])] ; ids=[c['change_id'] for c in plan.get('ordered_file_changes',[])]
    if confirmation.get('plan_candidate_reference',{}).get('plan_candidate_fingerprint')!=plan.get('plan_candidate_fingerprint'): raise ActivationError('wrong_plan_reference_rejected')
    if sorted(confirmation.get('confirmed_paths') or [])!=sorted(paths): raise ActivationError('confirmed_paths_exact_required')
    if any(c.get('risk_level')=='high' for c in plan.get('ordered_file_changes',[])) and not confirmation.get('risk_acknowledgements'): raise ActivationError('risk_acknowledgement_required')
    body={'schema':CONFIRM_SCHEMA,'plan_candidate_reference':_ref(plan),'human_actor':confirmation['human_actor'],'decision':dec,'confirmed_paths':paths,'confirmed_change_ids':ids,'confirmed_test_targets':plan.get('test_strategy',{}).get('required_test_targets',[]),'risk_acknowledgements':confirmation.get('risk_acknowledgements',[]),'scope_acknowledgement':confirmation.get('scope_acknowledgement','exact confirmed scope only'),'notes':confirmation.get('notes',''),'authority':AUTHORITY}
    return canon(body,'confirmation_fingerprint','confirmation_id','engineering-multifile-confirmation-')

def revise_multifile_change_plan(plan, human_revision_input):
    return build_multifile_change_plan_candidate(confirmed_specification={'confirmed_scope':[c['path'] for c in plan.get('ordered_file_changes',[])]}, work_request={'requested_scope':[c['path'] for c in plan.get('ordered_file_changes',[])],'repository_identity':plan.get('repository_identity',{})}, repository_analysis={}, repository_identity=plan.get('repository_identity',{}), human_operation_hints=human_revision_input, previous_plan_reference=_ref(plan), revision_reason=human_revision_input.get('revision_reason','human requires revision'), human_revision_input=human_revision_input)

def formalize_confirmed_multifile_plan(*, plan, confirmation, approved_proposal, authorization, operation_definitions, confirmed_specification, work_request, repository_analysis=None, workspace_root='.'):
    if plan.get('plan_status')=='rejected' or confirmation.get('decision')!='confirmed': return {'formalization_status':'rejected','reason':'plan_not_confirmed'}
    if confirmation.get('plan_candidate_reference',{}).get('plan_candidate_fingerprint')!=plan.get('plan_candidate_fingerprint'): return {'formalization_status':'rejected','reason':'wrong_plan_reference_rejected'}
    if any(c.get('operation_definition_status')=='requires_human_definition' for c in plan.get('ordered_file_changes',[])) and not operation_definitions: return {'formalization_status':'manual_operation_definition_required'}
    by={o.get('change_id'):dict(o) for o in operation_definitions}
    ops=[]
    for cid in plan['dependency_order']:
        c=next(x for x in plan['ordered_file_changes'] if x['change_id']==cid)
        if cid not in by: return {'formalization_status':'manual_operation_definition_required','missing_change_id':cid}
        op={k:v for k,v in by[cid].items() if k!='change_id'}; op.setdefault('target_path',c['path']); op.setdefault('operation_id',cid); ops.append(op)
    for t in plan.get('test_strategy',{}).get('required_test_targets',[]): ops.append({'operation_id':'test-'+fingerprint(t)[:8],'operation_type':'run_bounded_test','target_path':t.split('::')[0],'test_targets':[t],'flags':['-q'],'timeout_seconds':plan['test_strategy'].get('timeout_per_target',120)})
    pkg=build_governed_change_package(confirmed_specification=confirmed_specification, work_request=work_request, read_only_analysis=repository_analysis or {}, proposal=approved_proposal, operation_plan=ops, repository_identity=plan.get('repository_identity'), workspace_root=workspace_root, approval=approved_proposal, authorization=authorization)
    return {'formalization_status':'change_package_created','change_package':pkg}

def run_bounded_test_set(change_package, ordered_targets, *, workspace_root='.', stop_policy='first_failure', total_timeout_seconds=360, maximum_output_bytes=24000):
    results=[]; outbytes=0; failed=False
    pol=bounded_test_policy(maximum_output_bytes=maximum_output_bytes)
    for t in ordered_targets:
        if failed and stop_policy=='first_failure': results.append({'target':t,'status':'not_executed'}); continue
        r=run_bounded_test_operation({'operation_type':'run_bounded_test','target_path':str(t).split('::')[0],'test_targets':[t],'flags':['-q'],'timeout_seconds':min(120,total_timeout_seconds)}, Path(workspace_root), pol); r['target']=t; results.append(r); outbytes+=len(str(r.get('stdout','')))+len(str(r.get('stderr',''))); failed=r.get('status')!='passed'
        if outbytes>maximum_output_bytes: break
    status='passed' if all(r.get('status')=='passed' for r in results) and len(results)==len(ordered_targets) else 'failed' if any(r.get('status')=='failed' for r in results) else 'partially_executed'
    body={'schema':TEST_SET_SCHEMA,'change_package_reference':_ref(change_package),'ordered_results':results,'total_targets':len(ordered_targets),'executed_targets':sum(r.get('status')!='not_executed' for r in results),'passed_targets':sum(r.get('status')=='passed' for r in results),'failed_targets':sum(r.get('status')=='failed' for r in results),'timed_out_targets':sum(r.get('status')=='timed_out' for r in results),'not_executed_targets':[r['target'] for r in results if r.get('status')=='not_executed'],'stop_policy':stop_policy,'overall_status':status}
    return canon(body,'test_set_fingerprint','test_set_id','engineering-bounded-test-set-')

def v41_preview(plan=None, confirmation=None, package=None):
    return {'schema':'zero.engineering.multifile_preview.v1','multi_file_plan':_ref(plan or {}),'file_roles':{c['path']:c['file_role'] for c in (plan or {}).get('ordered_file_changes',[])},'dependency_order':(plan or {}).get('dependency_order',[]),'production_changes':[c['path'] for c in (plan or {}).get('ordered_file_changes',[]) if c.get('file_role')=='production'],'test_changes':[c['path'] for c in (plan or {}).get('ordered_file_changes',[]) if c.get('file_role')=='test'],'acceptance_mappings':(plan or {}).get('acceptance_criterion_mappings',[]),'test_execution_order':(plan or {}).get('test_strategy',{}).get('execution_order',[]),'risk_summary':(plan or {}).get('risk_summary'),'human_plan_confirmation':_ref(confirmation or {}),'package_binding':_ref(package or {}),'mutation_occurred':False,'tests_executed':False,'authorization_consumed':False,'repair_candidate_created':False}

def inspect_multifile_state(bundle):
    p=bundle.get('planning/multifile-change-plan-candidate.json'); c=bundle.get('planning/multifile-change-plan-confirmation.json'); ts=bundle.get('testing/bounded-test-set-result.json'); fe=bundle.get('testing/test-failure-evidence.json'); rc=bundle.get('feedback/repair-proposal-candidate.json'); rv=bundle.get('feedback/repair-candidate-review.json'); changes=(p or {}).get('ordered_file_changes',[])
    spec=bundle.get('work-entry/specification-confirmation.json'); wr=bundle.get('work-entry/request.json'); ra=bundle.get('work-entry/stages/repository-analysis.json') or bundle.get('work-entry/intake-repository-evidence.json')
    validation=validate_multifile_change_plan_candidate(p,confirmed_specification=spec,work_request=wr,repository_analysis=ra,session_id=(p or {}).get('session_id')) if p else {'plan_validation_status':'not_initialized','errors':[]}
    initialized='initialized' if p else 'incomplete' if any(bundle.get(x) for x in ('work-entry/specification-candidate.json','work-entry/specification-confirmation.json','work-entry/request.json')) else 'not_initialized'
    return {'multifile_coding_workflow_status':initialized,'multifile_plan_status':(p or {}).get('plan_status','not_initialized'),'multifile_plan_candidate_id':(p or {}).get('plan_candidate_id'),'multifile_plan_validation_status':validation['plan_validation_status'],'missing_linkage_reason':validation['errors'][0] if validation.get('errors') else None,'plan_confirmation_status':(c or {}).get('decision','not_started'),'planned_file_count':len(changes),'production_file_count':sum(x.get('file_role')=='production' for x in changes),'test_file_count':sum(x.get('file_role')=='test' for x in changes),'dependency_status':'valid' if validation.get('valid') else 'not_initialized','test_strategy_status':'ready' if (p or {}).get('test_strategy') else 'not_initialized','test_set_status':(ts or {}).get('overall_status','not_started'),'failed_test_count':(ts or {}).get('failed_targets',0),'failure_evidence_status':(fe or {}).get('evidence_status','not_started'),'repair_candidate_status':(rc or {}).get('candidate_status','not_started'),'repair_review_status':(rv or {}).get('decision','pending' if rc else 'not_started'),'iteration_number':len((bundle.get('iterations/iteration-index.json') or {}).get('iterations',[])),'iteration_limit':ITERATION_POLICY['maximum_recorded_iterations'],'next_governed_action':resume_multifile_state(bundle)['decision']}

def resume_multifile_state(bundle):
    if not bundle.get('planning/multifile-change-plan-candidate.json'): d='requires_multifile_plan'
    elif bundle['planning/multifile-change-plan-candidate.json'].get('plan_status')=='requires_clarification': d='requires_plan_clarification'
    elif not bundle.get('planning/multifile-change-plan-confirmation.json'): d='requires_plan_confirmation'
    elif not bundle.get('work-entry/governed-change-package.json'): d='requires_change_package'
    elif not bundle.get('execution/practical-execution-evidence.json'): d='requires_execution'
    elif not bundle.get('testing/bounded-test-set-result.json'): d='requires_test_set_execution'
    elif not bundle.get('testing/test-failure-evidence.json') and (bundle.get('testing/bounded-test-set-result.json') or {}).get('overall_status')!='passed': d='requires_failure_analysis'
    elif bundle.get('testing/test-failure-evidence.json') and not bundle.get('feedback/repair-proposal-candidate.json'): d='requires_repair_candidate'
    elif bundle.get('feedback/repair-proposal-candidate.json') and not bundle.get('feedback/repair-candidate-review.json'): d='requires_repair_review'
    else: d='requires_completion_review'
    return {'schema':'zero.engineering.multifile_resume.v1','decision':d,'will_modify_repository':False,'will_execute_tests':False,'will_create_repair_candidate':False,'will_approve':False,'will_authorize':False,'will_retry':False,'will_complete':False}
