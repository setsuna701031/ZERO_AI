import json, subprocess, sys
from pathlib import Path
import pytest
from core.engineering.engineering_work_entry import *
from core.engineering.engineering_work_entry import _stable, FLOW
from core.engineering.engineering_runtime_orchestrator_common import fingerprint

def req(**kw):
    d=dict(request_statement='deliver bounded work entry',repository_identity={'repo':'ZERO_AI'},repository_root_reference='.',requested_scope=['core/engineering'],excluded_scope=['docs/tmp'],requested_mode='governed_delivery')
    d.update(kw); return create_engineering_work_request(**d)
def intake(r=None): return admit_engineering_work(r or req())
def coord():
    r=req(); i=intake(r); return create_work_coordination(r,i)
def art(schema='zero.engineering.evidence.v1', aid='a', session_id=None):
    b={'schema':schema,'artifact_id':aid,'status':'closed'}
    if session_id: b['session_id']=session_id
    b['fingerprint']=fingerprint(b); return b

def step_to(c, target):
    keys={'repository_admission':'repository_admission','repository_analysis':'repository_analysis_closure','objective_definition':'objective','planning':'planning_closure','proposal_preparation':'proposal','proposal_review':'proposal_review_closure','awaiting_approval':'approval_closure'}
    while c['current_stage']!=target:
        nxt=FLOW[FLOW.index(c['current_stage'])+1]
        c=advance_work_coordination(c, art(aid=keys.get(nxt,nxt)), keys.get(nxt,nxt))
    return c

def test_deterministic_work_request_stable_request_id(): assert req()==req()
@pytest.mark.parametrize('name,kwargs,err',[('empty_request_rejection',{'request_statement':''},'empty_request_rejection'),('unsafe_repository_root_rejection',{'repository_root_reference':'/tmp/x'},'unsafe_repository_root_rejection'),('empty_scope_rejection',{'requested_scope':[]},'empty_scope_rejection'),('unbounded_scope_rejection',{'requested_scope':['*']},'unbounded_scope_rejection'),('invalid_mode_rejection',{'requested_mode':'auto_execute'},'invalid_mode_rejection'),('authority_payload_rejection',{'constraints':['approval=true']},'authority_payload_rejection')])
def test_work_request_rejections(name,kwargs,err):
    with pytest.raises(WorkEntryError, match=err): req(**kwargs)
def test_fake_schema_rejection():
    r=req(); r['schema']='zero.test.fake';
    with pytest.raises(WorkEntryError): admit_engineering_work(r)
def test_valid_intake_admission_scope_normalization_and_no_authority():
    i=intake(req(requested_scope=['core/engineering','core/engineering']))
    assert i['admission_status']=='admitted' and i['bounded_scope']==['core/engineering'] and not i['governance_requirements']['mutation_authority_granted']
def test_invalid_request_fingerprint_and_prohibited_payload_rejection():
    r=req(); r['work_request_fingerprint']='bad'
    with pytest.raises(WorkEntryError): admit_engineering_work(r)
    with pytest.raises(WorkEntryError): req(constraints=['shell_fragment'])
def test_create_coordination_link_existing_runtime_session_deterministic_initial_stage_correct():
    r=req(); i=intake(r); c=create_work_coordination(r,i); c2=create_work_coordination(r,i)
    assert c==c2 and c['current_stage']=='intake' and c['runtime_session_reference']['artifact_identity']
def test_duplicate_coordination_rejection_mixed_session_rejection():
    c=coord();
    with pytest.raises(WorkEntryError): advance_work_coordination(c, art(session_id='other'), 'repository_admission')

def test_stage_state_machine_happy_path_to_awaiting_approval_and_human_gate():
    c=coord()
    for key in ['repository_admission','repository_analysis_closure','objective','planning_closure','proposal','proposal_review_closure','proposal_review_closure']:
        c=advance_work_coordination(c, art(aid=key), key)
    assert c['current_stage']=='awaiting_approval' and c['next_governed_action']=='requires_human_approval'
    h=create_human_gate_handoff(c); assert h['authority_state']=='not_granted' and h['requested_human_action']=='approve'
@pytest.mark.parametrize('target,key',[('analysis_without_closure_rejected','wrong'),('objectives_without_artifact_rejected','wrong'),('planning_without_closure_rejected','wrong')])
def test_missing_stage_artifacts_rejected(target,key):
    c=coord();
    with pytest.raises(WorkEntryError): advance_work_coordination(c, art(), key)
def test_invalid_stage_jump_rejected_terminal_coordination_rejected():
    c=coord();
    with pytest.raises(WorkEntryError): advance_work_coordination(c, art(), 'proposal_review_closure')
    bad={**c,'current_stage':'closed'}; bad=_stable({k:v for k,v in bad.items() if k not in {'coordination_id','coordination_fingerprint'}},'coordination_fingerprint','coordination_id','engineering-work-coordination-')
    with pytest.raises(WorkEntryError): advance_work_coordination(bad, art(), 'x')

def test_approval_authorization_post_approval_flow_external_only():
    c=step_to(coord(),'awaiting_approval')
    c=advance_work_coordination(c, art(aid='approval'), 'approval_closure'); assert c['current_stage']=='awaiting_authorization'
    c=advance_work_coordination(c, art(aid='authorization'), 'authorization_closure'); assert c['current_stage']=='execution_preparation'
    c=advance_work_coordination(c, art(aid='prep'), 'execution_preparation_closure'); assert c['current_stage']=='ready_for_execution'
    c=advance_work_coordination(c, art(aid='ready'), 'execution_readiness'); assert c['current_stage']=='execution'
    c=advance_work_coordination(c, art(aid='result'), 'execution_result'); assert c['current_stage']=='verification'
    c=advance_work_coordination(c, art(aid='verify'), 'verification_closure'); assert c['current_stage']=='progress_evaluation'

def test_read_only_preparation_scenario_no_authority_no_execution():
    c=step_to(coord(),'awaiting_approval'); ins=inspect_work_coordination(c)
    assert ins['next_governed_action']=='requires_human_approval' and ins['execution_status']=='not_started'

def test_v34_completion_and_invalid_iteration_routes_are_human_gated():
    c=coord(); c={**c,'current_stage':'completion_review','completion_readiness':'prepare_completion_review'}; c=_stable({k:v for k,v in c.items() if k not in {'coordination_id','coordination_fingerprint'}},'coordination_fingerprint','coordination_id','engineering-work-coordination-')
    assert resume_work_coordination(c)['will_complete'] is False and inspect_work_coordination(c)['human_action_required']
    c={**c,'current_stage':'next_iteration','iteration_health':'stalled'}; c=_stable({k:v for k,v in c.items() if k not in {'coordination_id','coordination_fingerprint'}},'coordination_fingerprint','coordination_id','engineering-work-coordination-')
    assert resume_work_coordination(c)['will_create_proposal_automatically'] is False

def test_inspect_resume_journal_checkpoint_persistence_read_only(tmp_path):
    c=coord(); before=list(tmp_path.rglob('*')); ins=inspect_work_coordination(c); dec=resume_work_coordination(c)
    j=make_journal(c,['work_request_created','work_intake_admitted','work_coordination_created']); cp=make_checkpoint(c,j)
    assert list(tmp_path.rglob('*'))==before and ins==inspect_work_coordination(c) and dec['will_execute'] is False and j['events'][0]['event']=='work_request_created' and cp['current_stage']=='intake'
    out=persist_work_entry(tmp_path, c['runtime_session_reference']['artifact_identity'], coordination=c)
    assert out['work_entry_status']=='initialized'

def test_cli_submit_inspect_resume_invalid_input(tmp_path):
    p=subprocess.run([sys.executable,'-m','cli.zero_engineering_work','submit','--statement','x','--repo-id','r','--scope','core'],text=True,capture_output=True)
    assert p.returncode==0 and json.loads(p.stdout)['coordination']
    c=json.loads(p.stdout)['coordination']; f=tmp_path/'c.json'; f.write_text(json.dumps(c,sort_keys=True,separators=(',',':'))+'\n')
    assert subprocess.run([sys.executable,'-m','cli.zero_engineering_work','inspect',str(f)],capture_output=True).returncode==0
    assert subprocess.run([sys.executable,'-m','cli.zero_engineering_work','resume',str(f)],capture_output=True).returncode==0
    assert subprocess.run([sys.executable,'-m','cli.zero_engineering_work','submit','--statement','','--repo-id','r','--scope','core'],capture_output=True).returncode==2
