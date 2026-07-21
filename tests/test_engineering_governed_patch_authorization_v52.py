from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path

import pytest

from core.engineering.engineering_governed_patch_authorization import *
from core.engineering.engineering_governed_patch_authoring import snapshot_patch_sources
from core.engineering.engineering_multifile_coding_workflow import canon
from core.engineering.engineering_practical_task_runner import _ref
from core.engineering.engineering_runtime_session_store import read_session_artifact, write_session_artifact


def artifact(schema, name, **extra):
    return canon({'schema': schema, 'session_id': 'session-v52', **extra}, f'{name}_fingerprint', f'{name}_id', f'engineering-{name}-')


def prepared(tmp_path):
    root=tmp_path/'repo'; (root/'app').mkdir(parents=True); (root/'tests').mkdir()
    (root/'app/bug.py').write_text('VALUE = 1\n',encoding='utf-8',newline='')
    (root/'tests/test_bug.py').write_text('assert True\n',encoding='utf-8',newline='')
    items=[{'patch_item_id':'patch-0001','path':'app/bug.py','depends_on':[]},{'patch_item_id':'patch-0002','path':'tests/test_bug.py','depends_on':['patch-0001']}]
    patch=artifact('zero.engineering.patch_candidate.v1','patch',ordered_patch_items=items)
    intake=artifact('zero.engineering.patch_authoring_intake.v1','intake',repository_identity={'repository_id':'repo-v52'},confirmed_scope=['app/bug.py','tests/test_bug.py'],confirmed_paths=['app/bug.py','tests/test_bug.py'],confirmed_test_targets=['tests/test_bug.py'],iteration_reference={'iteration':1},confirmed_patch_item_ids=['patch-0001','patch-0002'])
    snapshots=snapshot_patch_sources(intake,patch,workspace_root=root)
    edits=[{'schema':'zero.engineering.file_edit_candidate.v1','path':'app/bug.py','patch_item_id':'patch-0001','candidate_edit_kind':'replace_exact_text','candidate_content':'VALUE = 2\n','candidate_diff':'-VALUE = 1\n+VALUE = 2','acceptance_criteria':['value fixed']},{'schema':'zero.engineering.test_edit_candidate.v1','path':'tests/test_bug.py','patch_item_id':'patch-0002','candidate_edit_kind':'replace_exact_text','candidate_content':'assert 1 == 1\n','candidate_diff':'-assert True\n+assert 1 == 1','acceptance_criteria':['bounded test']}]
    edits=[canon(x,'edit_fingerprint','edit_id','engineering-edit-') for x in edits]
    files={'edits':[edits[0]]}; tests={'edits':[edits[1]]}; diff=artifact('zero.engineering.candidate_diff.v1','diff',ordered_paths=['app/bug.py','tests/test_bug.py'])
    authored_review=artifact('zero.engineering.authored_patch_review.v1','authored_review',decision='confirmed',candidate_diff_reference=_ref(diff),confirmed_paths=['app/bug.py','tests/test_bug.py'],confirmed_edit_ids=[x['edit_id'] for x in edits],confirmed_test_edits=['tests/test_bug.py'])
    prep=build_change_package_preparation(work_request={},human_plan_confirmation={},reproduction_result={},repair_strategy={},patch_candidate=patch,human_patch_review={},authoring_intake=intake,candidate_diff=diff,authoring_validation={'validation_status':'valid'},human_authored_patch_review=authored_review,source_snapshots=snapshots,repository_identity=intake['repository_identity'],workspace_snapshot_reference={},confirmed_scope=intake['confirmed_scope'],iteration_reference=intake['iteration_reference'],session_id='session-v52')
    package=build_change_package_candidate(prep,intake,snapshots,files,tests,diff,patch)
    return root,patch,intake,snapshots,files,tests,diff,authored_review,prep,package


def validate(p, package=None, **changes):
    args=dict(preparation=p[8],candidate_diff=p[6],source_snapshots=p[3],file_edits=p[4],test_edits=p[5],human_authored_patch_review=p[7],patch_candidate=p[1],authoring_intake=p[2],workspace_root=p[0],repository_identity=p[2]['repository_identity'],session_id='session-v52',iteration_reference={'iteration':1}); args.update(changes)
    return validate_change_package_candidate(package or p[9],**args)


def test_preparation_requires_valid_and_confirmed_authoring(tmp_path):
    p=prepared(tmp_path); kwargs=dict(work_request={},human_plan_confirmation={},reproduction_result={},repair_strategy={},patch_candidate=p[1],human_patch_review={},authoring_intake=p[2],candidate_diff=p[6],authoring_validation={'validation_status':'invalid'},human_authored_patch_review=p[7],source_snapshots=p[3],repository_identity={},workspace_snapshot_reference={},confirmed_scope=[],iteration_reference={},session_id='session-v52')
    with pytest.raises(PatchAuthorizationError,match='authored_patch_validation_required'): build_change_package_preparation(**kwargs)
    kwargs['authoring_validation']={'validation_status':'valid'}; kwargs['human_authored_patch_review']={**p[7],'decision':'rejected'}
    with pytest.raises(PatchAuthorizationError,match='authored_patch_review_not_confirmed'): build_change_package_preparation(**kwargs)


def test_candidate_is_deterministic_bounded_and_has_no_authority(tmp_path):
    p=prepared(tmp_path); again=build_change_package_candidate(p[8],p[2],p[3],p[4],p[5],p[6],p[1])
    assert p[9]==again and p[9]['operation_count']==2 and p[9]['execution_authority']=='not_granted'
    assert p[9]['ordered_operations'][1]['depends_on']==['operation-0001'] and not any(p[9]['authority'].values())


@pytest.mark.parametrize(('mutation','reason'),[('operation','unknown_operation'),('count','operation_count_mismatch'),('scope','silent_scope_expansion'),('acceptance','missing_acceptance_mapping'),('verification','unbounded_verification_plan'),('rollback','missing_rollback_plan'),('authority','authority_payload_rejection')])
def test_candidate_validation_fails_closed(tmp_path,mutation,reason):
    p=prepared(tmp_path); package=copy.deepcopy(p[9])
    if mutation=='operation': package['ordered_operations'][0]['operation_type']='shell'
    elif mutation=='count': package['operation_count']=99
    elif mutation=='scope': package['ordered_operations'][0]['path']='outside.py'; package['ordered_paths'][0]='outside.py'
    elif mutation=='acceptance': package['ordered_operations'][0]['acceptance_criteria']=[]
    elif mutation=='verification': package['verification_plan']['bounded']=False
    elif mutation=='rollback': package['rollback_plan']['required']=False
    elif mutation=='authority': package['authority']['may_execute']=True
    package=canon({k:v for k,v in package.items() if k not in {'change_package_fingerprint','change_package_id'}},'change_package_fingerprint','change_package_id','engineering-governed-change-package-')
    assert reason in validate(p,package)['reason_codes']


def test_workspace_and_identity_lineage_drift_fail_closed(tmp_path):
    p=prepared(tmp_path); (p[0]/'app/bug.py').write_text('VALUE = 9\n',encoding='utf-8')
    assert 'workspace_drift' in validate(p)['reason_codes']
    p=prepared(tmp_path/'again'); assert 'wrong_repository_identity' in validate(p,repository_identity={'repository_id':'other'})['reason_codes']


def approved_chain(p):
    validation=validate(p); approval=review_change_package(p[9],validation,{'human_actor':'alice','decision':'approved','change_package_candidate_reference':_ref(p[9]),'approved_paths':p[9]['ordered_paths'],'approved_operation_ids':[x['operation_id'] for x in p[9]['ordered_operations']],'scope_acknowledgement':True})
    request=build_authorization_request(p[9],approval); decision=decide_patch_authorization(request,p[9],approval,{'human_actor':'bob','decision':'authorized','authorization_request_reference':_ref(request)}); authorized=build_authorized_change_package(p[9],approval,decision)
    return validation,approval,request,decision,authorized


def test_approval_and_authorization_require_human_and_exact_lineage(tmp_path):
    p=prepared(tmp_path); validation=validate(p)
    with pytest.raises(PatchAuthorizationError,match='human_actor_required'): review_change_package(p[9],validation,{})
    approval=review_change_package(p[9],validation,{'human_actor':'a','decision':'rejected','change_package_candidate_reference':_ref(p[9])})
    with pytest.raises(PatchAuthorizationError,match='approval_required'): build_authorization_request(p[9],approval)
    _,approval,request,_,_=approved_chain(p)
    with pytest.raises(PatchAuthorizationError,match='stale_authorization'): decide_patch_authorization(request,p[9],approval,{'human_actor':'b','decision':'authorized','authorization_request_reference':{}})


def test_authorized_package_rejects_substitution(tmp_path):
    p=prepared(tmp_path); _,approval,request,decision,_=approved_chain(p); decision={**decision,'authorized_paths':['other.py']}
    with pytest.raises(PatchAuthorizationError,match='path_substitution'): build_authorized_change_package(p[9],approval,decision)


def test_readiness_stops_at_explicit_apply_and_blocks_replay(tmp_path):
    p=prepared(tmp_path); _,approval,_,decision,authorized=approved_chain(p); ready=verify_patch_readiness(authorized,p[9],approval,decision,source_snapshots=p[3],authoring_intake=p[2],patch_candidate=p[1],workspace_root=p[0])
    assert ready['readiness_status']=='ready_for_explicit_apply' and ready['next_governed_action']=='awaiting_explicit_apply' and ready['executor']=='not_invoked'
    blocked=verify_patch_readiness({**authorized,'replay_status':'used'},p[9],approval,decision,source_snapshots=p[3],authoring_intake=p[2],patch_candidate=p[1],workspace_root=p[0]); assert {'authorization_already_used','authorization_replay'}<=set(blocked['reason_codes'])


def test_revision_inspect_resume_store_and_cli_surface(tmp_path):
    p=prepared(tmp_path); revised=revise_change_package_candidate(p[9],{'human_actor':'alice','change_package_candidate_reference':_ref(p[9]),'revision_reason':'tighten risk','updates':{'risk_summary':'reviewed risk'}}); assert revised['previous_change_package_reference']==_ref(p[9])
    bundle={'patch-authoring/review.json':p[7],STORE_FILES['preparation']:p[8],STORE_FILES['candidate']:p[9]}; assert resume_patch_authorization_state(bundle)['decision']=='requires_change_package_validation'; assert inspect_patch_authorization_state(bundle)['change_package_candidate_status']=='candidate'
    for path in STORE_FILES.values(): write_session_artifact(tmp_path,'session-v52',path,{'schema':'test'}); assert read_session_artifact(tmp_path,'session-v52',path)=={'schema':'test'}
    cp=subprocess.run([sys.executable,'-m','cli.zero_engineering_work','--help'],cwd=Path(__file__).parents[1],text=True,capture_output=True); assert cp.returncode==0
    for command in ('prepare-change-package','validate-change-package','review-change-package','build-patch-authorization-request','authorize-patch','authorized-change-package','verify-patch-readiness'): assert command in cp.stdout
    assert 'apply-patch' not in cp.stdout and '--auto-authorize' not in cp.stdout
