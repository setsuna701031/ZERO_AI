from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
import pytest
from core.engineering.engineering_execution_session import create_engineering_execution_session, validate_engineering_execution_session, seal_session
from core.engineering.engineering_execution_controller import attach_approval, attach_authorization, attach_preparation, attach_token, attach_execution_result, attach_verification_result, complete_execution_session, close_execution_session, EngineeringExecutionError
from core.engineering.engineering_execution_session_persistence import persist_execution_session, load_execution_session, resume_persisted_execution_session
from core.engineering.engineering_execution_session_report import build_execution_session_report, validate_execution_session_report
from core.engineering import engineering_execution_controller as ctl

def art(name, ident, status='accepted', **kw):
    d={'schema':'zero.engineering.'+name+'.v1','status':status, name+'_id':ident, 'fingerprint':'a'*64}
    d.update(kw); return d
@pytest.fixture(autouse=True)
def fake_adapter(monkeypatch): monkeypatch.setattr(ctl, '_phase_validate', lambda phase, artifact: None)
def base():
    task={'task_id':'task-1','repository_identity':{'root':'repo','head':'abc'}}
    proposal={'proposal_id':'proposal-1','fingerprint':'1'*64,'repository_identity':task['repository_identity']}
    linkage={'proposal_linkage_id':'link-1','fingerprint':'2'*64,'task_id':'task-1','repository_identity':task['repository_identity']}
    return create_engineering_execution_session(task=task, proposal=proposal, proposal_linkage=linkage)
def test_deterministic_identity_validation_and_denials():
    s1=base(); s2=base(); assert s1['execution_session_id']==s2['execution_session_id']; assert s1['fingerprint']==s2['fingerprint']; assert s1['current_stage']=='awaiting_approval'
    bad=dict(s1); bad['current_stage']='closed'; bad['fingerprint']=s1['fingerprint']; assert 'current_stage_not_derived' in validate_engineering_execution_session(bad)['errors']
    bad=seal_session({**s1,'command':'git status'}); assert 'executable_or_authority_payload_denied' in validate_engineering_execution_session(bad)['errors']
    bad=dict(s1); bad['deterministic']=False; assert not validate_engineering_execution_session(bad)['valid']
def test_attach_chain_replay_and_conflict():
    s=base(); approval=art('approval_decision','approval-1', decision='approved', proposal_identity=s['proposal_identity'])
    s=attach_approval(s, approval); assert s['current_stage']=='approved'
    assert attach_approval(s, approval)['replay_count']==1
    with pytest.raises(EngineeringExecutionError): attach_approval(s, {**approval,'approval_decision_id':'approval-2'})
    auth=art('authorization_decision','auth-1', decision='authorized', approval_identity='approval-1')
    prep={'schema':'zero.engineering.mutation_preparation_closure.v1','status':'closed','closure_id':'prep-1','fingerprint':'b'*64}
    token={'schema':'zero.engineering.mutation_preparation_token.v1','status':'issued','token_id':'tok-1','fingerprint':'c'*64,'token_consumed':False,'token_use_limit':1}
    execution={'schema':'zero.engineering.workspace_mutation_result.v1','status':'succeeded','result_id':'exec-1','fingerprint':'d'*64}
    verification={'schema':'zero.engineering.verification_result.v1','status':'passed','verification_status':'passed','verification_result_id':'ver-1','fingerprint':'e'*64,'execution_identity':'exec-1'}
    completion={'schema':'zero.engineering.completion.v1','status':'completed','completion_status':'completed','completion_id':'comp-1','fingerprint':'f'*64}
    closure={'schema':'zero.engineering.task_closure.v1','status':'closed','closure_id':'close-1','fingerprint':'0'*64}
    s=attach_authorization(s,auth); s=attach_preparation(s,prep); s=attach_token(s,token); assert s['current_stage']=='ready_for_execution'
    s=attach_execution_result(s,execution); s=attach_verification_result(s,verification); s=complete_execution_session(s, completion=completion); s=close_execution_session(s,closure)
    assert s['current_stage']=='closed'; assert [x['stage'] for x in s['stage_history']][-1]=='closed'
def test_ordering_rejections():
    s=base()
    with pytest.raises(EngineeringExecutionError): attach_authorization(s, art('authorization_decision','a'))
    with pytest.raises(EngineeringExecutionError): attach_preparation(s, art('prep','p'))
    with pytest.raises(EngineeringExecutionError): attach_token(s, art('token','t'))
def test_persistence_resume_report_bounded(tmp_path: Path):
    s=base(); p=tmp_path/'session.json'; persisted=persist_execution_session({**s,'bounded_summary':{'operation_count':1,'token_secret':'NO'}}, p)
    text=p.read_text(); assert 'token_secret' not in text and 'mutation_payload' not in text
    loaded=load_execution_session(p); assert loaded['fingerprint']==persisted['fingerprint']
    resumed=resume_persisted_execution_session(p); assert resumed['resume_count']==1 and resumed['current_stage']=='awaiting_approval'
    report=build_execution_session_report(resumed); assert validate_execution_session_report(report)['valid']; assert 'NO' not in json.dumps(report)
def test_cli_strict_json_validate(tmp_path: Path):
    s=base(); inp=tmp_path/'in.json'; inp.write_text(json.dumps({'session':s}))
    r=subprocess.run([sys.executable,'-m','cli.zero_engineering_execution','validate-session','--input',str(inp)], cwd=Path(__file__).parents[1], text=True, capture_output=True)
    assert r.returncode==0 and json.loads(r.stdout)['valid'] is True and r.stderr==''
