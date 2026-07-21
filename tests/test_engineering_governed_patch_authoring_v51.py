from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path

import pytest

from core.engineering.engineering_governed_patch_authoring import *
from core.engineering.engineering_multifile_coding_workflow import canon
from core.engineering.engineering_practical_task_runner import _ref
from core.engineering.engineering_runtime_session_store import read_session_artifact, write_session_artifact


def artifact(schema,name,**extra): return canon({'schema':schema,'session_id':'session-v51',**extra},f'{name}_fingerprint',f'{name}_id',f'engineering-{name}-')


def prepared(tmp_path):
    root=tmp_path/'repo'; (root/'app').mkdir(parents=True); (root/'tests').mkdir()
    (root/'app/bug.py').write_text('VALUE = 1\n\ndef value():\n    return VALUE\n',encoding='utf-8',newline='')
    (root/'tests/test_bug.py').write_text('from app.bug import value\n\ndef test_value():\n    assert value() == 1\n',encoding='utf-8',newline='')
    items=[{'patch_item_id':'patch-0001','path':'app/bug.py','file_role':'production','change_kind':'modify','change_intent':'adjust reviewed value behavior','related_symbols':['value'],'depends_on':[],'related_acceptance_criteria':['value is 2'],'repository_evidence':[{'path':'app/bug.py'}],'expected_test_impact':'covered by test_value','risk_level':'medium','operation_definition_status':'requires_human_definition'},{'patch_item_id':'patch-0002','path':'tests/test_bug.py','file_role':'test','change_kind':'modify','change_intent':'align reviewed assertion','related_symbols':['test_value'],'depends_on':['patch-0001'],'related_acceptance_criteria':['value is 2'],'repository_evidence':[{'path':'tests/test_bug.py'}],'expected_test_impact':'direct','risk_level':'low','operation_definition_status':'requires_human_definition'}]
    patch=artifact('zero.engineering.patch_candidate.v1','patch',repository_identity={'repository_id':'repo-v51'},confirmed_scope=['app/bug.py','tests/test_bug.py'],ordered_patch_items=items,dependency_order=['patch-0001','patch-0002'],authority=AUTHORITY)
    validation=artifact('zero.engineering.patch_candidate_validation.v1','patch_validation',validation_status='valid',patch_candidate_reference=_ref(patch)); strategy=artifact('zero.engineering.repair_strategy_candidate.v1','strategy'); impact=artifact('zero.engineering.repair_impact_analysis.v1','impact'); iteration={'iteration':1,'session_id':'session-v51'}
    review=artifact('zero.engineering.patch_candidate_review.v1','patch_review',patch_candidate_reference=_ref(patch),human_actor='alice',decision='confirmed',confirmed_paths=['app/bug.py','tests/test_bug.py'],confirmed_patch_item_ids=['patch-0001','patch-0002'],confirmed_test_targets=['tests/test_bug.py::test_value'],scope_acknowledgement=True)
    intake=build_patch_authoring_intake(patch_candidate=patch,patch_validation=validation,human_patch_review=review,repair_strategy=strategy,impact_analysis=impact,repository_identity={'repository_id':'repo-v51'},confirmed_scope=['app/bug.py','tests/test_bug.py'],iteration_reference=iteration,session_id='session-v51')
    snapshots=snapshot_patch_sources(intake,patch,workspace_root=root)
    definitions=[{'patch_item_id':'patch-0001','path':'app/bug.py','candidate_edit_kind':'replace_exact_text','old_text':'VALUE = 1','new_text':'VALUE = 2'},{'patch_item_id':'patch-0002','path':'tests/test_bug.py','candidate_edit_kind':'replace_exact_text','old_text':'value() == 1','new_text':'value() == 2'}]
    files,tests=author_file_edits(intake,patch,snapshots,definitions); diff=build_candidate_diff(intake,snapshots,files,tests)
    return root,patch,validation,review,strategy,impact,iteration,intake,snapshots,definitions,files,tests,diff


def test_authoring_intake_requires_valid_patch_and_confirmed_human_review(tmp_path):
    p=prepared(tmp_path); kwargs=dict(patch_candidate=p[1],patch_validation=p[2],human_patch_review=p[3],repair_strategy=p[4],impact_analysis=p[5],repository_identity={'repository_id':'repo-v51'},confirmed_scope=['app/bug.py','tests/test_bug.py'],iteration_reference=p[6],session_id='session-v51')
    bad=dict(kwargs); bad['patch_validation']={**p[2],'validation_status':'invalid'}
    with pytest.raises(PatchAuthoringError,match='patch_validation_required'): build_patch_authoring_intake(**bad)
    bad=dict(kwargs); bad['human_patch_review']={**p[3],'decision':'rejected'}
    with pytest.raises(PatchAuthoringError,match='patch_review_not_confirmed'): build_patch_authoring_intake(**bad)
    bad=dict(kwargs); bad['human_patch_review']={**p[3],'human_actor':''}
    with pytest.raises(PatchAuthoringError,match='human_actor_required'): build_patch_authoring_intake(**bad)


def test_stale_patch_and_unconfirmed_items_fail_closed(tmp_path):
    p=prepared(tmp_path); review={**p[3],'patch_candidate_reference':{}}
    with pytest.raises(PatchAuthoringError,match='stale_patch_candidate'): build_patch_authoring_intake(patch_candidate=p[1],patch_validation=p[2],human_patch_review=review,repair_strategy=p[4],impact_analysis=p[5],repository_identity={'repository_id':'repo-v51'},confirmed_scope=[],iteration_reference=p[6],session_id='session-v51')


def test_source_snapshot_is_deterministic_bounded_and_contains_no_absolute_path(tmp_path):
    p=prepared(tmp_path); again=snapshot_patch_sources(p[7],p[1],workspace_root=p[0]); assert p[8]==again
    assert all(not x['repository_relative_path'].startswith(str(p[0])) for x in p[8]['sources'])
    assert all(x['encoding']=='utf-8' and len(x['file_sha256'])==64 for x in p[8]['sources'])


def test_binary_and_oversized_sources_rejected(tmp_path):
    p=prepared(tmp_path); (p[0]/'app/bug.py').write_bytes(b'\x00\xff')
    with pytest.raises(PatchAuthoringError,match='binary_source_file'): snapshot_patch_sources(p[7],p[1],workspace_root=p[0])
    (p[0]/'app/bug.py').write_text('x'*(MAX_FILE_BYTES+1),encoding='utf-8')
    with pytest.raises(PatchAuthoringError,match='oversized_source_file'): snapshot_patch_sources(p[7],p[1],workspace_root=p[0])


@pytest.mark.parametrize('old', ['', 'MISSING', 'VALUE'])
def test_exact_replacement_requires_one_unique_match(tmp_path,old):
    p=prepared(tmp_path); definition={'patch_item_id':'patch-0001','path':'app/bug.py','candidate_edit_kind':'replace_exact_text','old_text':old,'new_text':'X'}
    with pytest.raises(PatchAuthoringError,match='exact_match_not_unique'): author_file_edits(p[7],p[1],p[8],[definition])


def test_candidate_content_and_diff_do_not_modify_repository(tmp_path):
    p=prepared(tmp_path); before=(p[0]/'app/bug.py').read_bytes(); edit=p[10]['edits'][0]
    assert 'VALUE = 2' in edit['candidate_content'] and 'VALUE = 1' in (p[0]/'app/bug.py').read_text(encoding='utf-8')
    assert (p[0]/'app/bug.py').read_bytes()==before and edit['authority']==AUTHORITY


def test_test_edits_require_confirmed_test_target(tmp_path):
    p=prepared(tmp_path); intake={**p[7],'confirmed_test_targets':[]}
    with pytest.raises(PatchAuthoringError,match='unconfirmed_test_target'): author_file_edits(intake,p[1],p[8],p[9])


def test_candidate_diff_is_deterministic_relative_and_has_no_timestamps(tmp_path):
    p=prepared(tmp_path); again=build_candidate_diff(p[7],p[8],p[10],p[11]); assert p[12]==again
    unified=p[12]['unified_diff']; assert '--- a/app/bug.py' in unified and '+++ b/tests/test_bug.py' in unified
    assert str(p[0]) not in unified and '\t20' not in unified and p[12]['diff_summary']['repository_modified'] is False


def validate(p,diff=None,**changes):
    args=dict(intake=p[7],patch_candidate=p[1],human_patch_review=p[3],source_set=p[8],file_edits=p[10],test_edits=p[11],workspace_root=p[0],repository_identity={'repository_id':'repo-v51'},session_id='session-v51',iteration_reference=p[6]); args.update(changes)
    return validate_authored_patch(diff or p[12],**args)


def test_authored_patch_validation_passes_without_repository_mutation(tmp_path):
    p=prepared(tmp_path); result=validate(p); assert result['valid'] and result['workspace_drift_status']=='not_detected'


def test_workspace_drift_and_source_fingerprint_fail_closed(tmp_path):
    p=prepared(tmp_path); (p[0]/'app/bug.py').write_text('VALUE = 9\n',encoding='utf-8'); result=validate(p)
    assert {'workspace_drift','source_fingerprint_mismatch'}<=set(result['reason_codes'])


@pytest.mark.parametrize(('mutation','reason'),[('scope','scope_expansion_required'),('item','unconfirmed_patch_item'),('test','unconfirmed_test_target'),('kind','unsupported_edit_kind'),('acceptance','missing_acceptance_mapping'),('impact','missing_test_impact'),('authority','authority_payload_rejection'),('diff','candidate_diff_mismatch')])
def test_validation_fail_closed_cases(tmp_path,mutation,reason):
    p=prepared(tmp_path); files=copy.deepcopy(p[10]); tests=copy.deepcopy(p[11]); diff=copy.deepcopy(p[12]); changes={}
    target=files['edits'][0] if mutation!='test' else tests['edits'][0]
    if mutation=='scope': target['path']='outside.py'
    elif mutation=='item': target['patch_item_reference']['patch_item_id']='old'
    elif mutation=='test': changes['intake']={**p[7],'confirmed_test_targets':[]}
    elif mutation=='kind': target['candidate_edit_kind']='rename'
    elif mutation=='acceptance': target['acceptance_criteria']=[]
    elif mutation=='impact': target['test_impact']=''
    elif mutation=='authority': target['authority']['may_execute']=True
    elif mutation=='diff': diff['unified_diff']='tampered'
    changes.update(file_edits=files,test_edits=tests)
    assert reason in validate(p,diff,**changes)['reason_codes']


def test_repository_session_iteration_and_review_mismatches(tmp_path):
    p=prepared(tmp_path)
    assert 'wrong_repository_identity' in validate(p,repository_identity={'repository_id':'other'})['reason_codes']
    assert 'session_mismatch' in validate(p,session_id='other')['reason_codes']
    assert 'iteration_mismatch' in validate(p,iteration_reference={'iteration':2})['reason_codes']
    assert 'patch_review_not_confirmed' in validate(p,human_patch_review={**p[3],'decision':'rejected'})['reason_codes']


def test_human_authored_patch_review_and_revision_lineage(tmp_path):
    p=prepared(tmp_path); validation=validate(p)
    with pytest.raises(PatchAuthoringError,match='human_actor_required'): review_authored_patch(p[12],p[10],p[11],validation,{})
    with pytest.raises(PatchAuthoringError,match='stale_candidate_diff'): review_authored_patch(p[12],p[10],p[11],validation,{'human_actor':'a','decision':'confirmed','candidate_diff_reference':{}})
    review=review_authored_patch(p[12],p[10],p[11],validation,{'human_actor':'alice','decision':'requires_revision','candidate_diff_reference':_ref(p[12])}); assert review['not_approval'] and review['not_change_package_admission']
    definitions=copy.deepcopy(p[9]); definitions[0]['new_text']='VALUE = 3'; files,tests=author_file_edits(p[7],p[1],p[8],definitions,previous_candidate_reference=_ref(p[12])); revised=build_candidate_diff(p[7],p[8],files,tests,previous_candidate_reference=_ref(p[12])); assert revised['previous_candidate_reference']==_ref(p[12]) and revised['candidate_diff_fingerprint']!=p[12]['candidate_diff_fingerprint']


def test_inspect_resume_session_store_and_cli_surface(tmp_path):
    p=prepared(tmp_path); bundle={'repair/patch-review.json':p[3],STORE_FILES['intake']:p[7],STORE_FILES['snapshots']:p[8],STORE_FILES['file_edits']:p[10],STORE_FILES['test_edits']:p[11],STORE_FILES['diff']:p[12]}; inspected=inspect_patch_authoring_state(bundle); assert inspected['file_edit_candidate_count']==1 and inspected['test_edit_candidate_count']==1
    resumed=resume_patch_authoring_state(bundle); assert resumed['decision']=='requires_authoring_validation' and not any(resumed[k] for k in ('will_author_edits','will_apply_patch','will_modify_repository','will_create_change_package','will_approve','will_authorize','will_execute','will_retry','will_complete'))
    for path in STORE_FILES.values(): write_session_artifact(tmp_path,'session-v51',path,{'schema':'test'}); assert read_session_artifact(tmp_path,'session-v51',path)=={'schema':'test'}
    cp=subprocess.run([sys.executable,'-m','cli.zero_engineering_work','--help'],cwd=Path(__file__).parents[1],text=True,capture_output=True); assert cp.returncode==0
    for command in ('build-patch-authoring-intake','snapshot-patch-sources','author-file-edits','validate-authored-patch','authored-patch','review-authored-patch','reject-authored-patch','revise-authored-patch'): assert command in cp.stdout
    assert 'create-change-package' not in cp.stdout and '--auto-confirm' not in cp.stdout
