from __future__ import annotations

import copy
import subprocess
import sys

import pytest

from core.engineering.engineering_governed_bug_reproduction import *
from core.engineering.engineering_practical_task_runner import _ref
from core.engineering.engineering_test_failure_analysis import build_test_failure_evidence
from core.engineering.engineering_repair_proposal_candidate import build_repair_proposal_candidate, review_repair_candidate
from core.engineering.engineering_runtime_session_store import read_session_artifact, write_session_artifact


def artifact(schema,prefix):
    body={'schema':schema,'session_id':'session-v45','value':prefix}
    return canon(body,f'{prefix}_fingerprint',f'{prefix}_id',f'engineering-{prefix}-')


def prepared(tmp_path,node='tests/test_bug.py::test_bug',failing=True):
    root=tmp_path/'repo'; (root/'tests').mkdir(parents=True); (root/'app').mkdir()
    (root/'app/bug.py').write_text('VALUE = 1\n',encoding='utf-8')
    assertion='assert 1 == 2' if failing else 'assert 1 == 1'
    (root/'tests/test_bug.py').write_text(f'def test_bug():\n    {assertion}\n',encoding='utf-8')
    work=artifact('zero.engineering.work_request.v1','work_request'); spec=artifact('zero.engineering.work_specification_confirmation.v1','confirmation'); plan_confirmation=artifact('zero.engineering.multifile_change_plan_confirmation.v1','plan_confirmation'); plan_confirmation['decision']='confirmed'; analysis=artifact('zero.engineering.repository_analysis.v1','analysis')
    identity={'repository_id':'repo-v45'}; scope=['app/bug.py','tests/test_bug.py']; snapshot=capture_workspace_snapshot(root,[node])
    request=build_reproduction_request_candidate(work_request=work,confirmed_specification=spec,human_plan_confirmation=plan_confirmation,repository_analysis=analysis,repository_identity=identity,confirmed_scope=scope,target_test_files=['tests/test_bug.py'],target_test_nodes=[node],expected_behavior='test passes',observed_behavior='test fails',reproduction_steps=['run confirmed target'],workspace_snapshot=snapshot,session_id='session-v45',timeout_seconds=30)
    raw={'reproduction_request_reference':_ref(request),'confirmed_test_targets':[node],'confirmed_scope':scope,'timeout_acknowledgement':True,'environment_acknowledgement':True,'human_actor':'alice','decision':'confirmed'}
    confirmation=confirm_reproduction_request(request,raw); admission=admit_bounded_reproduction(request,confirmation,workspace_snapshot=snapshot,repository_identity=identity,session_id='session-v45')
    return root,work,spec,plan_confirmation,analysis,identity,scope,snapshot,request,confirmation,admission


def test_requires_human_plan_confirmation(tmp_path):
    parts=prepared(tmp_path); plan=copy.deepcopy(parts[3]); plan['decision']='rejected'
    with pytest.raises(ReproductionError,match='human_plan_confirmation_required'):
        build_reproduction_request_candidate(work_request=parts[1],confirmed_specification=parts[2],human_plan_confirmation=plan,repository_analysis=parts[4],repository_identity=parts[5],confirmed_scope=parts[6],target_test_files=['tests/test_bug.py'],expected_behavior='pass',observed_behavior='fail',reproduction_steps=[],workspace_snapshot=parts[7],session_id='session-v45')


def test_candidate_is_canonical_and_has_no_authority(tmp_path):
    request=prepared(tmp_path)[8]
    assert not validate_reproduction_request(request,session_id='session-v45')
    assert request['authority']==AUTHORITY and not any(request['authority'].values())


def test_confirmation_requires_actor_and_exact_request(tmp_path):
    request=prepared(tmp_path)[8]
    with pytest.raises(ReproductionError,match='human_actor_required'): confirm_reproduction_request(request,{'decision':'confirmed'})
    with pytest.raises(ReproductionError,match='stale_confirmation'): confirm_reproduction_request(request,{'human_actor':'a','decision':'confirmed','reproduction_request_reference':{'artifact_identity':'old'}})


@pytest.mark.parametrize(('target','reason'),[
    ('../tests/test_bug.py','unsafe_test_target'),('app/bug.py','unsafe_test_target'),('tests/test_bug.py::test_bug or test_other','unsafe_test_target'),('','unsafe_test_target')])
def test_unsafe_targets_fail_closed(tmp_path,target,reason):
    request=copy.deepcopy(prepared(tmp_path)[8]); request['target_test_nodes']=[target]
    assert reason in validate_reproduction_request(request,session_id='session-v45')


def test_scope_timeout_session_repository_and_workspace_checks(tmp_path):
    parts=prepared(tmp_path); request=copy.deepcopy(parts[8]); request['confirmed_scope']=['app/bug.py']; request['timeout_policy']['seconds']=999; request['session_id']='other'
    errors=validate_reproduction_request(request,workspace_snapshot=parts[7],session_id='session-v45')
    assert {'scope_expansion','invalid_timeout','session_mismatch'}<=set(errors)
    rejected=admit_bounded_reproduction(parts[8],parts[9],workspace_snapshot=parts[7],repository_identity={'repository_id':'other'},session_id='session-v45')
    assert 'wrong_repository_identity' in rejected['reason_codes']


def test_bounded_failure_reproduces_and_consumes_admission_once(tmp_path):
    parts=prepared(tmp_path); result,test_set,consumed=run_reproduction(parts[8],parts[9],parts[10],workspace_root=parts[0],workspace_snapshot=parts[7])
    assert result['reproduction_status']=='reproduced' and result['reproduced'] is True
    assert test_set['failed_targets']==1 and consumed['consumption_state']=='consumed'
    with pytest.raises(ReproductionError,match='replayed_admission'): run_reproduction(parts[8],parts[9],consumed,workspace_root=parts[0],workspace_snapshot=parts[7])


def test_passing_target_is_not_reproduced(tmp_path):
    parts=prepared(tmp_path,failing=False); result,test_set,_=run_reproduction(parts[8],parts[9],parts[10],workspace_root=parts[0],workspace_snapshot=parts[7])
    assert result['reproduction_status']=='not_reproduced' and test_set['passed_targets']==1


def test_workspace_drift_blocks_execution(tmp_path):
    parts=prepared(tmp_path); (parts[0]/'tests/test_bug.py').write_text('def test_bug(): assert True\n',encoding='utf-8')
    with pytest.raises(ReproductionError,match='workspace_drift'): run_reproduction(parts[8],parts[9],parts[10],workspace_root=parts[0],workspace_snapshot=parts[7])


def test_first_failure_marks_remaining_not_executed(tmp_path):
    parts=prepared(tmp_path); root=parts[0]; (root/'tests/test_other.py').write_text('def test_other(): assert True\n',encoding='utf-8'); targets=['tests/test_bug.py::test_bug','tests/test_other.py::test_other']; snapshot=capture_workspace_snapshot(root,targets)
    request=build_reproduction_request_candidate(work_request=parts[1],confirmed_specification=parts[2],human_plan_confirmation=parts[3],repository_analysis=parts[4],repository_identity=parts[5],confirmed_scope=parts[6]+['tests/test_other.py'],target_test_files=['tests/test_bug.py','tests/test_other.py'],target_test_nodes=targets,expected_behavior='pass',observed_behavior='fail',reproduction_steps=[],workspace_snapshot=snapshot,session_id='session-v45',stop_policy='first_failure')
    confirmation=confirm_reproduction_request(request,{'reproduction_request_reference':_ref(request),'confirmed_test_targets':targets,'confirmed_scope':request['confirmed_scope'],'timeout_acknowledgement':True,'environment_acknowledgement':True,'human_actor':'a','decision':'confirmed'}); admission=admit_bounded_reproduction(request,confirmation,workspace_snapshot=snapshot,repository_identity=parts[5],session_id='session-v45')
    _,test_set,_=run_reproduction(request,confirmation,admission,workspace_root=root,workspace_snapshot=snapshot)
    assert test_set['not_executed_targets']==['tests/test_other.py::test_other']


def test_failure_evidence_is_bounded_and_root_cause_unconfirmed(tmp_path):
    parts=prepared(tmp_path); result,test_set,_=run_reproduction(parts[8],parts[9],parts[10],workspace_root=parts[0],workspace_snapshot=parts[7]); evidence=build_test_failure_evidence(execution=result,verification={},test_set=test_set,changed_paths=[],confirmed_scope=parts[6])
    assert evidence['failed_tests'][0]['failure_kind']=='assertion_failure'
    assert evidence['confirmed_root_cause'] is None and evidence['root_cause_status'] in {'suspected','unknown'}
    assert len(evidence['failed_tests'][0]['relevant_traceback_frames'])<=8


def test_repair_candidate_has_no_retry_execution_or_scope_expansion_authority(tmp_path):
    parts=prepared(tmp_path); result,test_set,_=run_reproduction(parts[8],parts[9],parts[10],workspace_root=parts[0],workspace_snapshot=parts[7]); evidence=build_test_failure_evidence(execution=result,verification={},test_set=test_set,changed_paths=[],confirmed_scope=parts[6]); candidate=build_repair_proposal_candidate(parent_work_request=parts[1],parent_change_package={},parent_execution=result,test_failure_evidence=evidence,confirmed_scope=parts[6])
    assert not candidate['authority']['may_retry'] and not candidate['authority']['may_execute'] and 'ordered_operations' not in candidate
    review=review_repair_candidate(candidate,{'human_actor':'alice','decision':'accept_for_planning'}); assert review['not_approval'] and review['not_authorization']


def test_inspect_resume_are_decision_only_and_legacy_is_not_corrupt(tmp_path):
    parts=prepared(tmp_path); bundle={'planning/multifile-change-plan-confirmation.json':parts[3],STORE_FILES['request']:parts[8]}
    assert inspect_reproduction_state(bundle)['reproduction_request_status']=='created'
    resumed=resume_reproduction_state(bundle); assert resumed['decision']=='requires_reproduction_confirmation'
    assert not any(resumed[k] for k in ('will_confirm','will_run_tests','will_retry','will_modify_repository','will_approve','will_authorize','will_complete'))
    assert resume_reproduction_state({})['decision']=='requires_plan_confirmation'


def test_session_store_paths_are_canonical_and_cli_surface_is_explicit(tmp_path):
    value={'schema':'test','status':'bounded'}
    for path in STORE_FILES.values():
        write_session_artifact(tmp_path,'session-v45',path,value); assert read_session_artifact(tmp_path,'session-v45',path)==value
    cp=subprocess.run([sys.executable,'-m','cli.zero_engineering_work','--help'],cwd=__import__('pathlib').Path(__file__).parents[1],text=True,capture_output=True)
    assert cp.returncode==0
    for command in ('build-reproduction-request','validate-reproduction-request','reproduction-request','confirm-reproduction','reject-reproduction','run-reproduction','reproduction-result'):
        assert command in cp.stdout
    assert '--auto-confirm' not in cp.stdout and '--yes' not in cp.stdout
