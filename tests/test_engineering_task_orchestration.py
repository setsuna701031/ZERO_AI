from core.engineering.engineering_task_orchestration import *
from core.engineering.engineering_task_orchestration_resume import resume_task
from tests import engineering_task_canonical_fixtures as cf
import pytest

def req(): return {'repository_identity':{'id':'repo','fingerprint':'r'},'requested_outcome':'change x','bounded_target_scope':['b','a'],'prohibited_scope':['z'],'requested_verification_expectations':['unit']}
def art(name, status='ok', **kw):
    return {'schema':f'zero.test.{name}.v1', f'{name}_id':f'{name}-1','fingerprint':f'fp-{name}','status':status, **kw}
def ready(tmp_path):
    s=create_task(tmp_path, req()); tid=s['task_id']; admit_task(tmp_path,tid); analysis=cf.analysis_report(); attach_analysis(tmp_path,tid,analysis); cand=cf.candidate_selection(task_id=tid, repository_identity=s['repository_identity'], analysis=analysis); attach_candidate_selection(tmp_path,tid,cand); attach_plan(tmp_path,tid,cf.repair_plan(cand)); attach_proposal(tmp_path,tid,cf.proposal()); return tid

def test_deterministic_task_creation(tmp_path):
    a=create_task(tmp_path, req()); b=create_task(tmp_path, dict(reversed(list(req().items()))))
    assert a['task_id']==b['task_id']; assert a['task_fingerprint']==b['task_fingerprint']
    c=create_task(tmp_path, {**req(),'requested_outcome':'different'}); assert c['task_id']!=a['task_id']


def test_fake_and_lookalike_artifacts_fail_closed(tmp_path):
    s=create_task(tmp_path, req()); tid=s['task_id']; admit_task(tmp_path, tid)
    with pytest.raises(Exception): attach_analysis(tmp_path, tid, art('analysis'))
    assert inspect_task(tmp_path, tid)['lifecycle_state']=='admitted'
    fake=cf.analysis_report(); fake['fingerprint']='0'*64
    with pytest.raises(Exception): attach_analysis(tmp_path, tid, fake)
    assert inspect_task(tmp_path, tid)['lifecycle_state']=='admitted'

def test_lifecycle_wait_and_replay(tmp_path):
    tid=ready(tmp_path); s=inspect_task(tmp_path,tid)
    assert s['lifecycle_state']=='awaiting_human_approval' and s['pending_requirement']=='human_approval'
    assert resume_task(tmp_path,tid)['lifecycle_state']=='awaiting_human_approval'
    with pytest.raises(Exception): execute_task(tmp_path,tid,{},tmp_path)
    approval=cf.approval_decision()
    a=attach_human_approval(tmp_path,tid,approval); assert a['lifecycle_state']=='approved'
    assert attach_human_approval(tmp_path,tid,approval)==a
    with pytest.raises(Exception): attach_human_approval(tmp_path,tid,{**approval, 'fingerprint':'0'*64})

def test_false_approval_and_out_of_order_fail(tmp_path):
    tid=ready(tmp_path)
    with pytest.raises(Exception): attach_human_approval(tmp_path,tid,art('approval','rejected', decision='rejected'))
    with pytest.raises(Exception): attach_authorization_token(tmp_path,tid,art('token','issued', token_consumed=False, use_limit=1))

def test_full_progression_with_monkeypatched_executor(tmp_path, monkeypatch):
    tid=ready(tmp_path); attach_human_approval(tmp_path,tid,cf.approval_decision())
    attach_authorization(tmp_path,tid,cf.authorization_decision())
    attach_preparation(tmp_path,tid,cf.preparation_closure())
    attach_authorization_token(tmp_path,tid,cf.authorization_token('tx-1'))
    calls=[]
    def fake(handoff, workspace_root, execute_confirmed=False):
        calls.append(1); return {'result':cf.execution_result(),'execution_evidence':{'schema':'zero.engineering.workspace_mutation_execution_evidence.v1','evidence_id':'ev-1','fingerprint':'evfp'},'execution_closure':{'schema':'zero.engineering.workspace_mutation_execution_closure.v1','closure_id':'tc-1','fingerprint':'tcfp'}}
    monkeypatch.setattr('core.engineering.engineering_governed_workspace_mutation_executor.execute_pipeline', fake)
    s=execute_task(tmp_path,tid,cf.executor_handoff(),tmp_path); assert s['lifecycle_state']=='executed' and calls==[1]
    with pytest.raises(Exception): execute_task(tmp_path,tid,{},tmp_path)
    v=cf.task_verification(tid, s['transaction_identity'])
    assert attach_verification(tmp_path,tid,v)['lifecycle_state']=='verified'
    c=close_task(tmp_path,tid); assert c['lifecycle_state']=='closed' and c['terminal'] is True
    with pytest.raises(Exception): attach_analysis(tmp_path,tid,art('analysis'))
