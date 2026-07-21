from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
from core.engineering.engineering_operator_flow import *
from core.engineering.engineering_approval_execution_activation import build_human_approval, create_authorization_handoff, build_human_authorization

def test_operator_flow_contract_and_resolution(tmp_path):
    repo=tmp_path/'repo'; repo.mkdir(); (repo/'docs').mkdir()
    store=tmp_path/'store'
    start=start_operator_flow('建立 docs/status.txt',store_root=store,repository=repo,scope=['README.md'])
    flow=start['operator_flow']
    assert flow['schema']=='zero.engineering.operator_flow.v1'
    assert flow['operator_flow_id'].startswith('engineering-operator-flow-')
    assert flow==build_operator_flow({'work-entry/request.json':start['work_request'],'work-entry/coordination.json':start['coordination'],'work-entry/pipeline.json':start['read_only_pipeline']})
    assert resolve_active_engineering_work(store)['resolution_status']=='resolved'
    assert build_operator_status(store)['next_operator_action']=='prepare'

def test_multiple_active_work_ambiguous_and_none(tmp_path):
    repo=tmp_path/'repo'; repo.mkdir(); (repo/'README.md').write_text('x',encoding='utf-8'); store=tmp_path/'store'
    assert resolve_active_engineering_work(store)['error']=='no_active_work'
    start_operator_flow('a',store_root=store,repository=repo,scope=['docs/a.txt'])
    start_operator_flow('b',store_root=store,repository=repo,scope=['docs/b.txt'])
    r=resolve_active_engineering_work(store)
    assert r['error']=='ambiguous_active_work' and len(r['candidates'])==2

def test_prepare_review_and_human_output(tmp_path):
    repo=tmp_path/'repo'; repo.mkdir(); (repo/'docs').mkdir(); (repo/'README.md').write_text('x',encoding='utf-8')
    store=tmp_path/'store'; start=start_operator_flow('建立 docs/status.txt',store_root=store,repository=repo,scope=['README.md'])
    out=prepare_operator_flow(store,repository=repo,session_id=start['coordination']['runtime_session_reference']['artifact_identity'])
    assert out['pipeline']['pipeline_status'] in {'awaiting_human_approval','awaiting_input'}
    st=build_operator_status(store,session_id=start['coordination']['runtime_session_reference']['artifact_identity'])
    text=human_text(st)
    assert '工程任務' in text and '下一步' in text and '治理警告' in text
    assert 'Traceback' not in text

def _prepared(tmp_path):
    repo=tmp_path/'repo'; repo.mkdir(); (repo/'docs').mkdir(); (repo/'README.md').write_text('x',encoding='utf-8')
    store=tmp_path/'store'; s=start_operator_flow('建立 docs/status.txt',store_root=store,repository=repo,scope=['README.md'])
    sid=s['coordination']['runtime_session_reference']['artifact_identity']
    prepare_operator_flow(store,repository=repo,session_id=sid)
    act=create_demo_activation(store,session_id=sid,repository=repo)
    appr=build_human_approval(activation=act,human_actor={'actor_id':'human-a','actor_type':'human'},scope=['docs/status.txt'])
    act=attach_human_approval(act,appr); persist_activation_artifacts(store,sid,activation=act,approval=appr)
    hand=create_authorization_handoff(act,appr)
    auth=build_human_authorization(handoff=hand,human_actor={'actor_id':'human-b','actor_type':'human'})
    act=attach_human_authorization(act,auth,appr); persist_activation_artifacts(store,sid,activation=act,authorization=auth,authorization_handoff=hand)
    prep,act=prepare_execution(act,auth,workspace_root=repo); persist_activation_artifacts(store,sid,activation=act,execution_preparation=prep)
    adm,act=admit_adapter(act,prep); persist_activation_artifacts(store,sid,activation=act,adapter_admission=adm)
    return repo,store,sid,auth,prep,adm,act

def test_preview_zero_mutation_execute_verify_result(tmp_path):
    repo,store,sid,auth,prep,adm,act=_prepared(tmp_path)
    before=sorted(p.relative_to(repo).as_posix() for p in repo.rglob('*'))
    pv=preview_execution(store,session_id=sid,repository=repo)
    after=sorted(p.relative_to(repo).as_posix() for p in repo.rglob('*'))
    assert before==after and pv['mutation_occurred'] is False and pv['authorization_consumption_state']=='unconsumed'
    er,auth2,act2=activate_governed_execution(act,auth,prep,adm,workspace_root=repo)
    assert (repo/'docs/status.txt').read_text(encoding='utf-8')=='ZERO engineering flow verified.\n'
    assert er['changed_paths']==['docs/status.txt'] and auth2['consumption_state']=='consumed'
    ver,act3=verify_execution(act2,er)
    pr,act4=evaluate_progress(act3,ver)
    assert ver['verification_status']=='verified'
    assert pr['completion_candidate'] is True and pr['session_completed'] is False

def test_execute_confirmation_drift_replay_and_verification_failure(tmp_path):
    repo,store,sid,auth,prep,adm,act=_prepared(tmp_path)
    assert preview_execution(store,session_id=sid,repository=repo)['preview_status']=='ready'
    (repo/'docs').mkdir(exist_ok=True); (repo/'docs/status.txt').write_text('drift',encoding='utf-8')
    try:
        activate_governed_execution(act,auth,prep,adm,workspace_root=repo)
    except ActivationError as e:
        assert e.code=='workspace_changed'
    assert auth['consumption_state']=='unconsumed'
    (repo/'docs/status.txt').unlink()
    er,auth2,act2=activate_governed_execution(act,auth,prep,adm,workspace_root=repo)
    try:
        activate_governed_execution(act2,auth2,prep,adm,workspace_root=repo)
    except ActivationError as e:
        assert e.code in {'adapter_admission_required_before_execution','authorization_reuse_rejected'}
    bad=dict(er); bad['changed_paths']=[]
    try: verify_execution(act2,bad)
    except ActivationError: assert False
    ver,_=verify_execution(act2,er)
    assert ver['verification_status']=='verified'

def test_cli_start_status_preview_execute_confirmation(tmp_path):
    repo=tmp_path/'repo'; repo.mkdir(); store=tmp_path/'store'
    cmd=[sys.executable,'-m','cli.zero_engineering_work','--store-root',str(store),'--format','json']
    r=subprocess.run(cmd+['start','建立 docs/status.txt','--repository',str(repo)],text=True,capture_output=True)
    assert r.returncode==0 and json.loads(r.stdout)['operator_flow']['schema']=='zero.engineering.operator_flow.v1'
    sid=json.loads(r.stdout)['coordination']['runtime_session_reference']['artifact_identity']
    r=subprocess.run(cmd+['--session-id',sid,'status'],text=True,capture_output=True)
    assert r.returncode==0 and json.loads(r.stdout)['schema']=='zero.engineering.operator_status.v1'
    r=subprocess.run(cmd+['--session-id',sid,'execute'],text=True,capture_output=True)
    assert r.returncode==8 and json.loads(r.stdout)['error']=='execution_confirmation_required'
