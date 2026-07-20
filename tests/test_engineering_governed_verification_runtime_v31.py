from __future__ import annotations
import json
import pytest
from core.engineering.engineering_mutation_transaction_common import fingerprint
from core.engineering.engineering_execution_session import seal_session
from core.engineering.engineering_verification_plan import build_verification_plan
from core.engineering.engineering_verification_plan_validation import validate_verification_plan
from core.engineering.engineering_verification_admission import build_verification_admission
from core.engineering.engineering_verification_admission_validation import validate_verification_admission
from core.engineering.engineering_governed_verification_runner import run_governed_verification
from core.engineering.engineering_runtime_continuation import build_runtime_continuation
from core.engineering.engineering_runtime_continuation_validation import validate_runtime_continuation
from core.engineering.engineering_task_artifact_adapter_registry import default_registry

def art(prefix, **kw):
    d=dict(kw); d['fingerprint']=fingerprint(d); d[prefix+'_id']='engineering-'+prefix+'-'+d['fingerprint'][:8]; return d

def fixture(tmp_path, vt='python_compile_files', target='pkg/a.py'):
    (tmp_path/'pkg').mkdir(exist_ok=True); (tmp_path/'pkg/a.py').write_text('x=1\n'); (tmp_path/'pkg/bad.py').write_text('def bad(:\n')
    proposal={'proposal_id':'proposal-1','fingerprint':'a'*64,'repository_identity':{'root':'tmp'}}
    repair={'repair_plan_id':'repair-1','fingerprint':'b'*64,'task_id':'task-1','repository_identity':{'root':'tmp'},'ordered_operation_ids':['op-1'],'allowed_target_paths':sorted(set(['pkg/a.py','pkg/bad.py',target])),'prohibited_target_paths':['secrets.txt'],'verification_expectations':[{'expectation_id':'exp-1','expectation_type':vt,'verification_type':vt,'required':True,'target_paths':[target]}]}
    execution={'result_id':'wsmut-result-1','fingerprint':'c'*64,'affected_target_paths':sorted(set(['pkg/a.py','pkg/bad.py',target])),'status':'succeeded'}
    session=seal_session({'execution_session_id':'engineering-execution-session-1','task_id':'task-1','repository_identity':{'root':'tmp'},'proposal_identity':'proposal-1','proposal_fingerprint':'a'*64,'execution_identity':'wsmut-result-1','execution_fingerprint':'c'*64})
    return session,proposal,repair,execution

def test_plan_is_deterministic_and_rejects_executable_payload(tmp_path):
    s,p,r,e=fixture(tmp_path)
    plan1=build_verification_plan(session=s,proposal=p,repair_plan=r,execution_result=e)
    plan2=build_verification_plan(session=s,proposal=p,repair_plan=r,execution_result=e)
    assert plan1==plan2 and validate_verification_plan(plan1).valid
    bad={**plan1,'verification_steps':[{**plan1['verification_steps'][0],'arguments':{'command':'pytest -k x; rm -rf /'}}]}
    bad['fingerprint']=fingerprint({k:v for k,v in bad.items() if k!='fingerprint'})
    assert not validate_verification_plan(bad).valid
    bad2={**plan1,'verification_steps':[{**plan1['verification_steps'][0],'target_reference':['/tmp/x']}]} ; bad2['fingerprint']=fingerprint({k:v for k,v in bad2.items() if k!='fingerprint'})
    assert not validate_verification_plan(bad2).valid

def test_admission_single_use_no_authority_and_adapter_registered(tmp_path):
    s,p,r,e=fixture(tmp_path); plan=build_verification_plan(session=s,proposal=p,repair_plan=r,execution_result=e); adm=build_verification_admission(plan)
    assert validate_verification_admission(adm,plan).valid and adm['single_use'] and adm['authority_boundary']['shell']=='not_granted'
    ref=default_registry().validate_artifact('verification_admission',adm)
    assert ref['validation_level']=='canonical_validator'

def test_compile_runner_pass_fail_and_replay(tmp_path):
    s,p,r,e=fixture(tmp_path); plan=build_verification_plan(session=s,proposal=p,repair_plan=r,execution_result=e); adm=build_verification_admission(plan)
    out=run_governed_verification(repository_root=tmp_path,session=s,proposal=p,repair_plan=r,execution_result=e,verification_plan=plan,verification_admission=adm)
    assert out['verification_run']['run_status']=='passed'; assert out['verification_result']['verification_status']=='passed'
    replay=run_governed_verification(repository_root=tmp_path,session=s,proposal=p,repair_plan=r,execution_result=e,verification_plan=plan,verification_admission=adm,replay_state=out)
    assert replay['replayed'] and replay['verification_run']['replay_count']==1
    s2,p2,r2,e2=fixture(tmp_path,target='pkg/bad.py'); plan2=build_verification_plan(session=s2,proposal=p2,repair_plan=r2,execution_result=e2); adm2=build_verification_admission(plan2)
    out2=run_governed_verification(repository_root=tmp_path,session=s2,proposal=p2,repair_plan=r2,execution_result=e2,verification_plan=plan2,verification_admission=adm2)
    assert out2['verification_run']['run_status']=='failed'; assert out2['verification_result']['verification_status']=='failed'

def test_file_json_static_and_continuation(tmp_path):
    (tmp_path/'pkg').mkdir(exist_ok=True); (tmp_path/'pkg/data.json').write_text('{"ok":true}'); (tmp_path/'pkg/safe.txt').write_text('hello')
    for vt,target in [('file_exists','pkg/data.json'),('json_parse','pkg/data.json'),('static_pattern_inspection','pkg/safe.txt')]:
        s,p,r,e=fixture(tmp_path,vt=vt,target=target); plan=build_verification_plan(session=s,proposal=p,repair_plan=r,execution_result=e); adm=build_verification_admission(plan)
        out=run_governed_verification(repository_root=tmp_path,session=s,proposal=p,repair_plan=r,execution_result=e,verification_plan=plan,verification_admission=adm)
        assert out['verification_run']['run_status']=='passed'
        cont=build_runtime_continuation(session=s,execution_result=e,verification_result=out['verification_result'],verification_run=out['verification_run'])
        assert cont['decision']=='continue_to_completion' and cont['retry_eligible'] is False and validate_runtime_continuation(cont).valid

def test_pytest_files_fixed_invocation_and_failure(tmp_path):
    (tmp_path/'tests').mkdir(); (tmp_path/'tests/test_ok.py').write_text('def test_ok():\n assert True\n'); (tmp_path/'tests/test_bad.py').write_text('def test_bad():\n assert False\n')
    s,p,r,e=fixture(tmp_path,vt='pytest_files',target='tests/test_ok.py'); r['allowed_target_paths'].append('tests/test_ok.py'); e['affected_target_paths'].append('tests/test_ok.py')
    plan=build_verification_plan(session=s,proposal=p,repair_plan=r,execution_result=e,maximum_duration_seconds=20); adm=build_verification_admission(plan)
    out=run_governed_verification(repository_root=tmp_path,session=s,proposal=p,repair_plan=r,execution_result=e,verification_plan=plan,verification_admission=adm)
    assert out['verification_run']['run_status']=='passed'
    s,p,r,e=fixture(tmp_path,vt='pytest_files',target='tests/test_bad.py'); r['allowed_target_paths'].append('tests/test_bad.py'); e['affected_target_paths'].append('tests/test_bad.py')
    plan=build_verification_plan(session=s,proposal=p,repair_plan=r,execution_result=e,maximum_duration_seconds=20); adm=build_verification_admission(plan)
    out=run_governed_verification(repository_root=tmp_path,session=s,proposal=p,repair_plan=r,execution_result=e,verification_plan=plan,verification_admission=adm)
    assert out['verification_run']['run_status']=='failed'
