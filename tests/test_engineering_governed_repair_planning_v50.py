from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path

import pytest

from core.engineering.engineering_governed_repair_planning import *
from core.engineering.engineering_multifile_coding_workflow import canon
from core.engineering.engineering_practical_task_runner import _ref
from core.engineering.engineering_runtime_session_store import read_session_artifact, write_session_artifact


def art(schema,name,**extra): return canon({'schema':schema,'session_id':'session-v50','value':name,**extra},f'{name}_fingerprint',f'{name}_id',f'engineering-{name}-')


def prepared(outside=False):
    work=art('zero.engineering.work_request.v1','work_request'); spec=art('zero.engineering.work_specification_confirmation.v1','confirmation',confirmed_acceptance_criteria=['failure no longer occurs']); plan=art('zero.engineering.multifile_change_plan_confirmation.v1','plan',decision='confirmed'); result=art('zero.engineering.bug_reproduction_result.v1','result',reproduction_status='reproduced')
    path='core/shared.py' if outside else 'app/bug.py'; suspected=[{'path':path,'evidence_reasons':['traceback_repository_path'],'confidence_band':'medium'}]
    failure=art('zero.engineering.test_failure_evidence.v1','evidence',suspected_related_paths=suspected,failed_tests=[{'test_node':'tests/test_bug.py::test_bug'}],confirmed_root_cause=None,root_cause_status='suspected')
    repair=art('zero.engineering.repair_proposal_candidate.v1','repair',test_failure_evidence_reference=_ref(failure),suspected_paths=suspected,candidate_status='ready_for_review')
    review=art('zero.engineering.repair_candidate_review.v1','review',repair_candidate_reference=_ref(repair),decision='accept_for_planning',human_actor='alice',not_approval=True,not_authorization=True)
    identity={'repository_id':'repo-v50'}; scope=['app/bug.py','tests/test_bug.py']; iteration={'iteration':1,'session_id':'session-v50'}
    planning=build_repair_planning_intake(work_request=work,confirmed_specification=spec,human_plan_confirmation=plan,reproduction_result=result,test_failure_evidence=failure,repair_proposal_candidate=repair,human_repair_review=review,repository_identity=identity,confirmed_scope=scope,iteration_reference=iteration,session_id='session-v50')
    hypothesis=build_root_cause_hypothesis(planning,failure,repair); repository={'schema':'zero.engineering.repository_analysis.v1','files':[{'path':'app/bug.py'},{'path':'tests/test_bug.py'},{'path':'core/shared.py'}]}; impact=build_repair_impact_analysis(planning,hypothesis,failure,repair,repository)
    strategy=build_repair_strategy_candidate(planning,hypothesis,impact)
    patch=None if outside else build_patch_candidate(planning,strategy,impact,acceptance_criteria=['failure no longer occurs'])
    return work,spec,plan,result,failure,repair,review,identity,scope,iteration,planning,hypothesis,repository,impact,strategy,patch


def test_planning_requires_failure_repair_and_accepted_human_review():
    p=prepared(); kwargs=dict(work_request=p[0],confirmed_specification=p[1],human_plan_confirmation=p[2],reproduction_result=p[3],test_failure_evidence=p[4],repair_proposal_candidate=p[5],human_repair_review=p[6],repository_identity=p[7],confirmed_scope=p[8],iteration_reference=p[9],session_id='session-v50')
    for key,reason in [('test_failure_evidence','missing_failure_evidence'),('repair_proposal_candidate','missing_repair_candidate'),('human_repair_review','missing_human_repair_review')]:
        bad=dict(kwargs); bad[key]={}
        with pytest.raises(RepairPlanningError,match=reason): build_repair_planning_intake(**bad)
    bad=dict(kwargs); bad['human_repair_review']={**p[6],'decision':'rejected'}
    with pytest.raises(RepairPlanningError,match='repair_review_not_accepted'): build_repair_planning_intake(**bad)


def test_root_cause_is_hypothesis_never_confirmation():
    hypothesis=prepared()[11]
    assert hypothesis['confirmed_root_cause'] is False and hypothesis['confidence_band'] in {'low','medium','high'}
    assert 'confirmed' not in hypothesis and 'proven_root_cause' not in hypothesis


def test_impact_analysis_separates_direct_and_possible_scope():
    within=prepared()[13]; outside=prepared(outside=True)[13]
    assert within['directly_affected_paths']==['app/bug.py'] and within['scope_relationship']=='within_confirmed_scope'
    assert outside['possibly_affected_paths']==['core/shared.py'] and outside['requires_human_scope_review']


def test_scope_expansion_blocks_patch_candidate():
    p=prepared(outside=True)
    with pytest.raises(RepairPlanningError,match='scope_expansion_required'): build_patch_candidate(p[10],p[14],p[13],acceptance_criteria=['x'])


def test_strategy_and_patch_are_high_level_deterministic_and_non_executable():
    p=prepared(); patch=p[15]; again=build_patch_candidate(p[10],p[14],p[13],acceptance_criteria=['failure no longer occurs'])
    assert patch==again and patch['dependency_order']==['patch-0001']
    assert patch['operation_definition_status']=='requires_human_definition' and patch['authority']==AUTHORITY
    text=str(patch).lower(); assert 'new_text' not in text and 'old_text' not in text and 'ordered_operations' not in patch


def validation(parts,patch=None,**changes):
    args=dict(planning=parts[10],strategy=parts[14],impact=parts[13],failure_evidence=parts[4],repair_candidate=parts[5],human_repair_review=parts[6],repository_analysis=parts[12],repository_identity=parts[7],session_id='session-v50',iteration_reference=parts[9]); args.update(changes)
    return validate_patch_candidate(patch or parts[15],**args)


def test_valid_patch_lineage_and_bounded_test_plan():
    result=validation(prepared()); assert result['valid'] and result['validation_status']=='valid'


@pytest.mark.parametrize(('mutation','reason'),[
    ('cycle','dependency_cycle'),('scope','silent_scope_expansion'),('acceptance','missing_acceptance_mapping'),('test','unbounded_test_plan'),('executable','executable_operation_prohibited'),('authority','authority_payload_rejection'),('session','session_mismatch'),('repository','wrong_repository_identity')])
def test_patch_validation_fail_closed(mutation,reason):
    parts=prepared(); patch=copy.deepcopy(parts[15]); changes={}
    if mutation=='cycle': patch['ordered_patch_items'][0]['depends_on']=['patch-0001']
    elif mutation=='scope': patch['ordered_patch_items'][0]['path']='outside/new.py'
    elif mutation=='acceptance': patch['ordered_patch_items'][0]['related_acceptance_criteria']=[]
    elif mutation=='test': patch['test_plan']['maximum_targets']=99; patch['test_plan']['timeout_seconds']=999
    elif mutation=='executable': patch['ordered_patch_items'][0]['replacement']='code'
    elif mutation=='authority': patch['authority']['may_execute']=True
    elif mutation=='session': changes['session_id']='other'
    elif mutation=='repository': changes['repository_identity']={'repository_id':'other'}
    assert reason in validation(parts,patch,**changes)['reason_codes']


def test_missing_stale_iteration_and_review_lineage_rejected():
    p=prepared()
    assert 'missing_failure_evidence' in validation(p,failure_evidence=None)['reason_codes']
    assert 'missing_repair_candidate' in validation(p,repair_candidate=None)['reason_codes']
    assert 'missing_human_repair_review' in validation(p,human_repair_review=None)['reason_codes']
    assert 'iteration_mismatch' in validation(p,iteration_reference={'iteration':2})['reason_codes']
    rejected={**p[6],'decision':'rejected'}; assert 'repair_review_not_accepted' in validation(p,human_repair_review=rejected)['reason_codes']


def test_human_patch_review_requires_actor_exact_fingerprint_and_is_not_approval():
    p=prepared(); valid=validation(p); patch=p[15]
    with pytest.raises(RepairPlanningError,match='human_actor_required'): review_patch_candidate(patch,valid,{})
    with pytest.raises(RepairPlanningError,match='stale_patch_candidate'): review_patch_candidate(patch,valid,{'human_actor':'a','decision':'confirmed','patch_candidate_reference':{}})
    review=review_patch_candidate(patch,valid,{'human_actor':'alice','decision':'confirmed','patch_candidate_reference':_ref(patch),'confirmed_paths':['app/bug.py'],'confirmed_patch_item_ids':['patch-0001'],'confirmed_test_targets':['tests/test_bug.py::test_bug'],'risk_acknowledgements':['root cause unconfirmed'],'scope_acknowledgement':True})
    assert review['not_approval'] and review['not_authorization'] and review['not_execution_permission']


def test_rejected_and_revision_reviews_do_not_create_new_patch():
    p=prepared(); valid=validation(p); patch=p[15]
    for decision in ('rejected','requires_revision'):
        review=review_patch_candidate(patch,valid,{'human_actor':'alice','decision':decision,'patch_candidate_reference':_ref(patch)}); assert review['decision']==decision
    revised=revise_patch_candidate(patch,{'revision_reason':'human requested clarification','blocking_questions':['clarify intended behavior']})
    assert revised['previous_patch_reference']==_ref(patch) and revised['patch_candidate_fingerprint']!=patch['patch_candidate_fingerprint']


def test_inspect_resume_and_session_store_are_decision_only(tmp_path):
    p=prepared(); bundle={'feedback/repair-review.json':p[6],STORE_FILES['planning_intake']:p[10],STORE_FILES['hypothesis']:p[11],STORE_FILES['impact']:p[13],STORE_FILES['strategy']:p[14],STORE_FILES['patch']:p[15]}
    assert inspect_repair_planning_state(bundle)['next_governed_action']=='requires_patch_validation'
    resumed=resume_repair_planning_state(bundle); assert not any(resumed[k] for k in ('will_confirm','will_modify_repository','will_create_change_package','will_approve','will_authorize','will_execute','will_retry','will_complete'))
    for path in STORE_FILES.values(): write_session_artifact(tmp_path,'session-v50',path,{'schema':'test'}); assert read_session_artifact(tmp_path,'session-v50',path)=={'schema':'test'}


def test_cli_surface_has_no_auto_confirmation():
    cp=subprocess.run([sys.executable,'-m','cli.zero_engineering_work','--help'],cwd=Path(__file__).parents[1],text=True,capture_output=True); assert cp.returncode==0
    for command in ('build-repair-planning-intake','root-cause-hypothesis','impact-analysis','repair-strategy','build-patch-candidate','validate-patch-candidate','patch-candidate','review-patch-candidate','reject-patch-candidate','revise-patch-candidate'): assert command in cp.stdout
    assert '--auto-confirm' not in cp.stdout and '--yes' not in cp.stdout
