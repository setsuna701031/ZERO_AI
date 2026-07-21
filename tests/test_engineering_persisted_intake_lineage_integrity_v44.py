from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.engineering.engineering_multifile_coding_workflow import (
    build_multifile_change_plan_candidate,
    inspect_multifile_state,
    resume_multifile_state,
    validate_multifile_change_plan_candidate,
)
from core.engineering.engineering_natural_language_intake import (
    STORE_FILES,
    build_finalized_intake,
    confirm_specification,
    create_formal_work_request_from_confirmed_specification,
    inspect_natural_language_intake,
    persist_finalized_intake,
    persist_formalized,
    start_natural_language_intake,
)
from core.engineering.engineering_runtime_session_store import load_session_store, read_session_artifact, write_session_artifact


def ref(value, identity, fingerprint):
    return {'schema': value['schema'], 'artifact_identity': value[identity], 'artifact_fingerprint': value[fingerprint], 'session_id': value.get('session_id')}


def governed(tmp_path):
    repo=tmp_path/'repo'; (repo/'docs').mkdir(parents=True); (repo/'docs/usage.md').write_text('usage\n',encoding='utf-8')
    store=tmp_path/'sessions'; started=start_natural_language_intake('update docs/usage.md documentation',store_root=store,repository=repo,repo_id='repo-v44')
    intake=started['natural_language_intake']; candidate=started['specification_candidate']; sid=intake['intake_id']
    raw={'specification_candidate_reference':ref(candidate,'specification_candidate_id','specification_candidate_fingerprint'),'human_actor':'alice','decision':'confirm','confirmed_scope':candidate['included_paths'],'confirmed_acceptance_criteria':candidate['acceptance_criteria'],'confirmed_constraints':['docs only'],'risk_acknowledgement':True}
    confirmation=confirm_specification(candidate,raw); write_session_artifact(store,sid,STORE_FILES['confirmation'],confirmation)
    finalized=persist_finalized_intake(store,sid,intake,candidate,confirmation)
    identity={'repository_id':'repo-v44',**started['repository_evidence']['repository_identity']}
    formalized=create_formal_work_request_from_confirmed_specification(candidate,confirmation,repository_identity=identity,finalized_intake=finalized)
    persist_formalized(store,sid,formalized); bundle=load_session_store(store,sid); request=bundle['work-entry/request.json']
    plan=build_multifile_change_plan_candidate(confirmed_specification=confirmation,work_request=request,repository_analysis=bundle[STORE_FILES['evidence']],repository_identity=identity,session_id=sid)
    write_session_artifact(store,sid,'planning/multifile-change-plan-candidate.json',plan); bundle=load_session_store(store,sid)
    return store,sid,bundle,intake,candidate,confirmation,finalized,request,plan


def validate(parts, *, plan=None, request=None, confirmation=None, finalized=None):
    _,sid,bundle,_,_,actual_confirmation,actual_finalized,actual_request,actual_plan=parts
    return validate_multifile_change_plan_candidate(plan or actual_plan,confirmed_specification=confirmation or actual_confirmation,work_request=request or actual_request,repository_analysis=bundle[STORE_FILES['evidence']],session_id=sid,finalized_intake=actual_finalized if finalized is None else finalized)


def test_finalized_intake_is_canonical_stable_and_persisted_in_originating_session(tmp_path):
    store,sid,bundle,intake,candidate,confirmation,finalized,_,_=governed(tmp_path)
    assert finalized==build_finalized_intake(intake,candidate,confirmation,session_id=sid)
    assert finalized==read_session_artifact(store,sid,STORE_FILES['finalized_intake'])
    assert bundle[STORE_FILES['finalized_intake']]['finalization_status']=='finalized'


def test_work_request_references_exact_finalized_intake_and_plan_is_valid(tmp_path):
    parts=governed(tmp_path); finalized=parts[6]; request=parts[7]
    assert request['source_actor_reference']['natural_language_lineage']=={**ref(finalized,'finalized_intake_id','finalized_intake_fingerprint'),'finalization_status':'finalized'}
    assert validate(parts)=={'valid':True,'errors':[],'plan_validation_status':'valid'}


@pytest.mark.parametrize(('mutation','reason'),[
    ('missing','missing_intake_reference'),('unresolved','unresolved_intake_reference'),('identity','wrong_intake_identity'),
    ('fingerprint','wrong_intake_fingerprint'),('session','intake_session_mismatch'),('pre_finalization','pre_finalization_intake_reference'),
    ('stale','stale_intake_reference'),('specification','wrong_specification_lineage'),
])
def test_lineage_fail_closed_reason_codes(tmp_path,mutation,reason):
    parts=governed(tmp_path); request=copy.deepcopy(parts[7]); finalized=copy.deepcopy(parts[6]); confirmation=parts[5]
    if mutation=='missing': request['source_actor_reference'].pop('natural_language_lineage')
    elif mutation=='unresolved': finalized=None
    elif mutation=='identity': request['source_actor_reference']['natural_language_lineage']['artifact_identity']='wrong'
    elif mutation=='fingerprint': request['source_actor_reference']['natural_language_lineage']['artifact_fingerprint']='wrong'
    elif mutation=='session': request['source_actor_reference']['natural_language_lineage']['session_id']='wrong'
    elif mutation=='pre_finalization': finalized['finalization_status']='candidate'
    elif mutation=='stale': request['source_actor_reference']['natural_language_lineage']=parts[4]['intake_reference']
    elif mutation=='specification': finalized['specification_confirmation_reference']['artifact_fingerprint']='wrong'
    if mutation=='unresolved':
        result=validate_multifile_change_plan_candidate(parts[8],confirmed_specification=confirmation,work_request=request,repository_analysis=parts[2][STORE_FILES['evidence']],session_id=parts[1],finalized_intake=None)
    else: result=validate(parts,request=request,finalized=finalized)
    assert reason in result['errors']


def test_missing_finalized_intake_is_legacy_incomplete_not_corrupt(tmp_path):
    parts=governed(tmp_path); bundle=dict(parts[2]); bundle.pop(STORE_FILES['finalized_intake'])
    inspected=inspect_multifile_state(bundle)
    assert inspected['multifile_plan_validation_status']=='invalid'
    assert inspected['missing_linkage_reason']=='missing_finalized_intake'
    assert 'unresolved_intake_reference' in validate_multifile_change_plan_candidate(bundle['planning/multifile-change-plan-candidate.json'],confirmed_specification=bundle[STORE_FILES['confirmation']],work_request=bundle['work-entry/request.json'],repository_analysis=bundle[STORE_FILES['evidence']],session_id=parts[1],finalized_intake=None)['errors']
    assert resume_multifile_state(bundle)['decision']=='requires_lineage_reconfirmation'


def test_inspect_reports_read_back_lineage_and_no_automatic_authority(tmp_path):
    store,sid,bundle,*_=governed(tmp_path); inspected=inspect_natural_language_intake(store,sid); resumed=resume_multifile_state(bundle)
    assert inspected['finalized_intake_status']=='finalized'
    assert inspected['lineage_resolvable'] and inspected['lineage_fingerprint_match'] and inspected['lineage_session_match']
    assert inspected['persisted_intake_path']==STORE_FILES['finalized_intake']
    assert resumed['decision']=='requires_plan_confirmation'
    assert not any(resumed[k] for k in ('will_modify_repository','will_execute_tests','will_approve','will_authorize','will_retry','will_complete'))


def test_cli_formalize_and_validate_use_persisted_finalized_intake(tmp_path):
    repo=tmp_path/'repo'; (repo/'docs').mkdir(parents=True); (repo/'docs/usage.md').write_text('usage\n',encoding='utf-8'); store=tmp_path/'sessions'; root=Path(__file__).parents[1]
    def run(*args): return subprocess.run([sys.executable,'-m','cli.zero_engineering_work','--store-root',str(store),*args],cwd=root,text=True,capture_output=True)
    started=run('intake','update docs/usage.md documentation','--repository',str(repo),'--repo-id','repo-v44-cli'); assert started.returncode==0,started.stdout+started.stderr
    payload=json.loads(started.stdout); candidate=payload['specification_candidate']; sid=payload['natural_language_intake']['intake_id']
    confirmation={'specification_candidate_reference':ref(candidate,'specification_candidate_id','specification_candidate_fingerprint'),'human_actor':'alice','decision':'confirm','confirmed_scope':candidate['included_paths'],'confirmed_acceptance_criteria':candidate['acceptance_criteria'],'confirmed_constraints':['docs only'],'risk_acknowledgement':True}
    confirmation_path=tmp_path/'confirmation.json'; confirmation_path.write_text(json.dumps(confirmation),encoding='utf-8')
    confirmed=run('--session-id',sid,'confirm-specification',str(confirmation_path)); assert confirmed.returncode==0,confirmed.stdout+confirmed.stderr
    formalized=run('--session-id',sid,'formalize'); assert formalized.returncode==0,formalized.stdout+formalized.stderr
    planned=run('--session-id',sid,'build-multifile-plan'); assert planned.returncode==0,planned.stdout+planned.stderr
    validated=run('--session-id',sid,'validate-multifile-plan'); assert validated.returncode==0,validated.stdout+validated.stderr
    assert json.loads(validated.stdout)['plan_validation_status']=='valid'
    status=json.loads(run('--session-id',sid,'inspect').stdout)
    assert status['finalized_intake_status']=='finalized' and status['lineage_resolvable']
