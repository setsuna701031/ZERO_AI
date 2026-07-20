from __future__ import annotations
import copy, json, subprocess, sys
import pytest
from core.engineering.engineering_completion_foundation import *
from core.engineering.engineering_task_artifact_adapter_registry import default_registry
from core.engineering.engineering_task_orchestration import *
from core.engineering.engineering_task_orchestration_resume import resume_task
from tests import engineering_task_canonical_fixtures as cf

def chain():
    analysis=cf.analysis_report(); cand=cf.candidate_selection('task-1','repo-1',analysis); plan=cf.repair_plan(cand); prop=cf.proposal(); link=build_proposal_linkage(task_id='task-1',repository_identity='repo-1',analysis=analysis,candidate=cand,repair_plan=plan,proposal=prop); exe=cf.execution_result(); ver=build_verification_result(task_id='task-1',repository_identity='repo-1',proposal=prop,repair_plan=plan,execution_result=exe,verification_status='passed',verification_expectation_results=[{'expectation_id':'verify-1','expectation_type':'focused_test_passed','status':'passed','summary':'ok','evidence_reference_ids':['e1']}],evidence_references=[{'evidence_reference_id':'e1','bounded_summary':'external'}]); comp=build_completion(task_id='task-1',repository_identity='repo-1',analysis_identity=analysis['repository_analysis_report_id'],candidate_identity=cand['candidate_id'],repair_plan=plan,proposal=prop,verification_result=ver); return analysis,cand,plan,prop,link,exe,ver,comp

def assert_bad(fn, art, **ctx):
    r=fn(art, **ctx); assert not r.valid

def test_proposal_linkage_deterministic_and_rejections():
    a,c,p,prop,link,exe,ver,comp=chain(); assert link==build_proposal_linkage(task_id='task-1',repository_identity='repo-1',analysis=a,candidate=c,repair_plan=p,proposal=prop)
    assert validate_proposal_linkage(link, task_id='task-1', repository_identity='repo-1', analysis=a, candidate=c, repair_plan=p, proposal=prop).valid
    muts=[{'repair_plan_identity':'x'},{'repair_plan_fingerprint':'0'*64},{'candidate_identity':'x'},{'analysis_identity':'x'},{'ordered_operation_ids':[]},{'ordered_operation_ids':link['ordered_operation_ids']+['x'],'operation_count':2},{'allowed_target_paths':['a','b']},{'prohibited_target_paths':[]},{'verification_expectation_ids':['other']},{'approval_granted':True},{'note':'git status'}]
    for m in muts:
        bad={**link, **m}; assert_bad(validate_proposal_linkage,bad, task_id='task-1', repository_identity='repo-1', analysis=a, candidate=c, repair_plan=p, proposal=prop)

def test_verification_result_deterministic_status_and_rejections():
    a,c,p,prop,link,exe,ver,comp=chain(); assert ver==chain()[6]
    assert validate_verification_result(ver, task_id='task-1', repository_identity='repo-1', proposal=prop, repair_plan=p, execution_result=exe).valid
    for m in [{'task_id':'x'},{'proposal_identity':'x'},{'repair_plan_identity':'x'},{'execution_identity':'x'},{'verification_expectation_results':[]},{'verification_expectation_results':ver['verification_expectation_results']*2},{'verification_expectation_results':[{'expectation_id':'unknown','expectation_type':'focused_test_passed','status':'passed','summary':'ok','evidence_reference_ids':[]}]},{'verification_status':'failed','status':'failed'},{'verification_status':'blocked','status':'blocked'},{'authorization_granted':True},{'note':'shell=True git status'}]:
        assert_bad(validate_verification_result,{**ver, **m}, task_id='task-1', repository_identity='repo-1', proposal=prop, repair_plan=p, execution_result=exe)

def test_completion_deterministic_and_rejections():
    a,c,p,prop,link,exe,ver,comp=chain(); assert comp==chain()[7]
    assert validate_completion(comp, task_id='task-1', repository_identity='repo-1', proposal=prop, verification_result=ver).valid
    failed={**ver,'verification_status':'failed','status':'failed'}
    for m,vr in [({'proposal_identity':'x'},ver), ({'verification_result_identity':'x'},ver), ({'task_id':'x'},ver), ({'immutable':False},ver), ({'approval_granted':True},ver), ({},failed)]:
        assert_bad(validate_completion,{**comp, **m}, task_id='task-1', repository_identity='repo-1', proposal=prop, verification_result=vr)

def test_adapters_and_orchestrator_persistence_replay(tmp_path, monkeypatch):
    a,c,p,prop,link,exe,ver,comp=chain(); reg=default_registry()
    assert reg.validate_artifact('proposal_linkage',link)['bounded_summary']['operation_count']==1
    assert reg.validate_artifact('verification_result',ver)['validation_status']=='passed'
    assert reg.validate_artifact('completion',comp)['validation_status']=='completed'
    with pytest.raises(Exception): reg.validate_artifact('verification_result',{**ver,'schema':'zero.engineering.verification_result.v2'})
    s=create_task(tmp_path, {'repository_identity':'repo-1','requested_outcome':'x','bounded_target_scope':['a'],'prohibited_scope':['secrets']}); tid=s['task_id']; admit_task(tmp_path,tid); a=cf.analysis_report(); c=cf.candidate_selection(tid,'repo-1',a); p=cf.repair_plan(c); prop=cf.proposal(); link=build_proposal_linkage(task_id=tid,repository_identity='repo-1',analysis=a,candidate=c,repair_plan=p,proposal=prop)
    with pytest.raises(Exception): attach_proposal(tmp_path,tid,{'proposal':prop,'proposal_linkage':link})
    attach_analysis(tmp_path,tid,a); attach_candidate_selection(tmp_path,tid,c); attach_plan(tmp_path,tid,p)
    st=attach_proposal(tmp_path,tid,{'proposal':prop,'proposal_linkage':link}); assert st['lifecycle_state']=='awaiting_human_approval'
    assert attach_proposal(tmp_path,tid,{'proposal':prop,'proposal_linkage':link})==st
    with pytest.raises(Exception): attach_proposal(tmp_path,tid,{'proposal':{**prop,'fingerprint':'0'*64},'proposal_linkage':link})
    attach_human_approval(tmp_path,tid,cf.approval_decision()); attach_authorization(tmp_path,tid,cf.authorization_decision()); attach_preparation(tmp_path,tid,cf.preparation_closure()); attach_authorization_token(tmp_path,tid,cf.authorization_token('tx-1'))
    monkeypatch.setattr('core.engineering.engineering_governed_workspace_mutation_executor.execute_pipeline', lambda h,w,execute_confirmed=False:{'result':cf.execution_result()})
    st=execute_task(tmp_path,tid,cf.executor_handoff(),tmp_path)
    with pytest.raises(Exception): attach_completion(tmp_path,tid,comp)
    plan_ref={'repair_plan_id':st['plan_identity']['artifact_identity'],'fingerprint':st['plan_identity']['artifact_fingerprint'], **st['plan_identity']['bounded_summary']}
    ver=build_verification_result(task_id=tid,repository_identity='repo-1',proposal=st['proposal_identity'],repair_plan=plan_ref,execution_result=st['execution_result_identity'],verification_status='passed',verification_expectation_results=[{'expectation_id':'verify-1','expectation_type':'focused_test_passed','status':'passed','summary':'ok','evidence_reference_ids':[]}])
    assert attach_verification_result(tmp_path,tid,ver)['lifecycle_state']=='verified'
    with pytest.raises(Exception): attach_verification_result(tmp_path,tid,{**ver,'fingerprint':'0'*64})
    comp=build_completion(task_id=tid,repository_identity='repo-1',analysis_identity=a['repository_analysis_report_id'],candidate_identity=c['candidate_id'],repair_plan=plan_ref,proposal=st['proposal_identity'],verification_result=ver)
    assert attach_completion(tmp_path,tid,comp)['lifecycle_state']=='completed'
    assert resume_task(tmp_path,tid)['completion_identity']['artifact_fingerprint']==comp['fingerprint']
    assert attach_completion(tmp_path,tid,comp)['completion_identity']['artifact_fingerprint']==comp['fingerprint']
    closed=close_task(tmp_path,tid); assert closed['terminal'] is True
    with pytest.raises(Exception): attach_completion(tmp_path,tid,comp)

def test_cli_build_validate_strict_json():
    a,c,p,prop,link,exe,ver,comp=chain()
    payload={'task_id':'task-1','repository_identity':'repo-1','analysis':a,'candidate':c,'repair_plan':p,'proposal':prop}
    r=subprocess.run([sys.executable,'cli/zero_engineering_task.py','build-proposal-linkage','--json',json.dumps(payload)],text=True,capture_output=True,check=False); assert r.returncode==0 and json.loads(r.stdout)['schema']==PROPOSAL_LINKAGE_SCHEMA
    r=subprocess.run([sys.executable,'cli/zero_engineering_task.py','validate-proposal-linkage','--json',json.dumps({'proposal_linkage':link,'analysis':a,'candidate':c,'repair_plan':p,'proposal':prop,'expected_task_id':'task-1','expected_repository_identity':'repo-1'})],text=True,capture_output=True,check=False); assert r.returncode==0 and json.loads(r.stdout)['valid'] is True
    r=subprocess.run([sys.executable,'cli/zero_engineering_task.py','build-verification-result','--json',json.dumps({'task_id':'task-1','repository_identity':'repo-1','proposal':prop,'repair_plan':p,'execution_result':exe,'verification_status':'passed','verification_expectation_results':ver['verification_expectation_results']})],text=True,capture_output=True,check=False); assert r.returncode==0 and json.loads(r.stdout)['schema']==VERIFICATION_RESULT_SCHEMA
    r=subprocess.run([sys.executable,'cli/zero_engineering_task.py','build-completion','--json',json.dumps({'task_id':'task-1','repository_identity':'repo-1','analysis_identity':a['repository_analysis_report_id'],'candidate_identity':c['candidate_id'],'repair_plan':p,'proposal':prop,'verification_result':ver})],text=True,capture_output=True,check=False); assert r.returncode==0 and json.loads(r.stdout)['schema']==COMPLETION_SCHEMA
    bad=subprocess.run([sys.executable,'cli/zero_engineering_task.py','validate-completion','--json',json.dumps({'completion':{**comp,'schema':'x'}})],text=True,capture_output=True,check=False); assert bad.returncode==2 and json.loads(bad.stdout)['valid'] is False
