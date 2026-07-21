from __future__ import annotations
import subprocess, sys
from pathlib import Path
import pytest
from core.engineering.engineering_practical_task_runner import *
from core.engineering.engineering_approval_execution_activation import ActivationError


def repo(tmp_path):
    (tmp_path/'docs').mkdir(); (tmp_path/'tests').mkdir(); subprocess.run(['git','init'],cwd=tmp_path,check=True,capture_output=True)
    return tmp_path

def spec(): return {'schema':'zero.engineering.confirmed_work_specification.v1','confirmed_specification_id':'s1','confirmed_scope':['docs','tests','app.py']}
def wr(): return {'schema':'zero.engineering.work_request.v1','work_request_id':'w1','requested_scope':['docs','tests','app.py'],'repository_identity':{'repository_id':'r'}}
def pkg(root, ops, scope=None):
    s=spec();
    if scope is not None: s['confirmed_scope']=scope
    return build_governed_change_package(confirmed_specification=s, work_request=wr(), operation_plan=ops, workspace_root=str(root), repository_identity={'repository_id':'r'})
def auth(p, scope=None, consumed='unconsumed'):
    return {'schema':'zero.engineering.human_execution_authorization.v1','authorization_id':'a','authorization_fingerprint':'afp','package_fingerprint':p['change_package_fingerprint'],'authorized_scope':scope or p['confirmed_scope'],'consumption_state':consumed}
def approval(p): return {'schema':'zero.engineering.human_approval.v1','decision':'approved','package_fingerprint':p['change_package_fingerprint']}
def exe(p, root, **kw): return execute_practical_change_package(p, approval=approval(p), authorization=auth(p, kw.pop('scope',None), kw.pop('consumed','unconsumed')), admitted=kw.pop('admitted',True), confirm_execution=kw.pop('confirm',True), workspace_root=root, **kw)

def test_deterministic_package_identity_and_order_stable(tmp_path):
    r=repo(tmp_path); ops=[{'operation_type':'create_text_file','target_path':'docs/a.txt','content':'a'}]
    assert pkg(r,ops)==pkg(r,ops); assert pkg(r,ops)['ordered_operations'][0]['operation_id']=='op-0001'

def test_package_requires_inputs_and_rejects_empty(tmp_path):
    with pytest.raises(ActivationError): build_governed_change_package(confirmed_specification=None, work_request=wr(), operation_plan=[{}])
    with pytest.raises(ActivationError): build_governed_change_package(confirmed_specification=spec(), work_request=None, operation_plan=[{}])
    with pytest.raises(ActivationError): build_governed_change_package(confirmed_specification=spec(), work_request=wr(), operation_plan=[])

def test_validation_rejections(tmp_path):
    r=repo(tmp_path); p=pkg(r,[{'operation_id':'x','operation_type':'create_text_file','target_path':'docs/a.txt','content':'a'},{'operation_id':'x','operation_type':'run_shell','target_path':'docs/b'}])
    v=validate_governed_change_package(p, workspace_root=r)
    assert 'duplicate_operation_id_rejected' in v['errors']; assert 'unsupported_operation_rejected' in v['errors']
    q=pkg(r,[{'operation_type':'create_text_file','target_path':'docs/a.txt','content':'a'},{'operation_type':'replace_text_exact','target_path':'docs/a.txt','old_text':'a','new_text':'b','before_state':{'sha256':'x'}}])
    assert 'conflicting_target_operations_rejected' in validate_governed_change_package(q,workspace_root=r)['errors']
    assert 'package_changed_after_approval_rejected' in validate_governed_change_package(q,workspace_root=r,approval={'package_fingerprint':'bad'})['errors']

@pytest.mark.parametrize('bad', ['/x','../x','.git/config','docs/../x'])
def test_safe_paths_rejected(tmp_path,bad):
    with pytest.raises(ActivationError): safe_path(tmp_path,bad)

def test_symlink_directory_and_binary_rejected(tmp_path):
    r=repo(tmp_path); (r/'docs/bin').write_bytes(b'\xff\xfe'); (r/'docs/dir').mkdir(); (r/'docs/link').symlink_to('/tmp')
    with pytest.raises(ActivationError): safe_path(r,'docs/bin')
    with pytest.raises(ActivationError): safe_path(r,'docs/link')
    p=pkg(r,[{'operation_type':'append_text','target_path':'docs/dir','append_content':'x','before_state':{'sha256':'x'}}])
    e=exe(p,r); assert e['execution_status']=='failed' or e['failure_classification'] in {'directory_target_rejected','missing_path'}

def test_create_append_remove_replace_and_replay(tmp_path):
    r=repo(tmp_path); p=pkg(r,[{'operation_type':'create_text_file','target_path':'docs/a.txt','content':'hello\n'}]); e=exe(p,r)
    assert e['execution_status']=='executed' and (r/'docs/a.txt').read_text()=='hello\n'
    assert exe(p,r)['execution_status']!='executed'
    h=sha_file(r/'docs/a.txt'); p2=pkg(r,[{'operation_type':'append_text','target_path':'docs/a.txt','append_content':'world\n','before_state':{'sha256':h}}]); assert exe(p2,r)['execution_status']=='executed'
    p3=pkg(r,[{'operation_type':'append_text','target_path':'docs/a.txt','append_content':'world\n','before_state':{'sha256':sha_file(r/'docs/a.txt')}}]); assert exe(p3,r)['execution_status']=='failed'
    h=sha_file(r/'docs/a.txt'); p4=pkg(r,[{'operation_type':'replace_text_exact','target_path':'docs/a.txt','old_text':'hello','new_text':'hi','expected_occurrence_count':1,'before_state':{'sha256':h}}]); assert exe(p4,r)['execution_status']=='executed'
    h=sha_file(r/'docs/a.txt'); p5=pkg(r,[{'operation_type':'remove_text_exact','target_path':'docs/a.txt','old_text':'world\n','expected_occurrence_count':1,'before_state':{'sha256':h}}]); assert exe(p5,r)['execution_status']=='executed'

def test_replace_mismatch_before_hash_duplicate_no_regex(tmp_path):
    r=repo(tmp_path); (r/'docs/a.txt').write_text('a a',encoding='utf-8')
    for op in [
        {'operation_type':'replace_text_exact','target_path':'docs/a.txt','old_text':'z','new_text':'x','expected_occurrence_count':1,'before_state':{'sha256':sha_file(r/'docs/a.txt')}},
        {'operation_type':'replace_text_exact','target_path':'docs/a.txt','old_text':'a','new_text':'x','expected_occurrence_count':1,'before_state':{'sha256':sha_file(r/'docs/a.txt')}},
        {'operation_type':'replace_text_exact','target_path':'docs/a.txt','old_text':'.*','new_text':'x','expected_occurrence_count':1,'before_state':{'sha256':'bad'}},
    ]:
        e=exe(pkg(r,[op]),r); assert e['mutation_occurred'] is False

def test_directory_rename_hash_preserved_and_rejections(tmp_path):
    r=repo(tmp_path); p=pkg(r,[{'operation_type':'create_directory','target_path':'docs/new'}]); assert exe(p,r)['operation_results'][0]['mutation_occurred']
    assert exe(p,r)['operation_results'][0]['status']=='already_exists'
    (r/'docs/a.txt').write_text('x',encoding='utf-8'); h=sha_file(r/'docs/a.txt')
    p2=pkg(r,[{'operation_type':'rename_file','source_path':'docs/a.txt','target_path':'docs/b.txt','before_state':{'sha256':h}}]); e=exe(p2,r); assert e['renamed_paths'][0]['content_hash_preserved']
    p3=pkg(r,[{'operation_type':'rename_file','source_path':'docs/missing.txt','target_path':'docs/c.txt','before_state':{'sha256':h}}]); assert exe(p3,r)['mutation_occurred'] is False
    (r/'docs/c.txt').write_text('c',encoding='utf-8'); p4=pkg(r,[{'operation_type':'rename_file','source_path':'docs/b.txt','target_path':'docs/c.txt','before_state':{'sha256':sha_file(r/'docs/b.txt')}}]); assert exe(p4,r)['execution_status']=='failed'

def test_transaction_prevalidates_and_rolls_back(tmp_path):
    r=repo(tmp_path); (r/'docs/a.txt').write_text('one',encoding='utf-8')
    p=pkg(r,[{'operation_type':'append_text','target_path':'docs/a.txt','append_content':' two','before_state':{'sha256':sha_file(r/'docs/a.txt')}},{'operation_type':'replace_text_exact','target_path':'docs/missing.txt','old_text':'x','new_text':'y','before_state':{'sha256':'bad'}}])
    e=exe(p,r); assert e['mutation_occurred'] is False and (r/'docs/a.txt').read_text()=='one'

def test_bounded_pytest_success_failure_timeout_and_policy(tmp_path):
    r=repo(tmp_path); (r/'tests/test_ok.py').write_text('def test_ok():\n assert True\n',encoding='utf-8'); (r/'tests/test_fail.py').write_text('def test_fail():\n assert False\n',encoding='utf-8')
    ok=run_bounded_test_operation({'operation_type':'run_bounded_test','target_path':'tests/test_ok.py','test_targets':['tests/test_ok.py'],'flags':['-q']},r); assert ok['status']=='passed' and ok['command_tokens'][:3]==[sys.executable,'-m','pytest']
    fail=run_bounded_test_operation({'operation_type':'run_bounded_test','target_path':'tests/test_fail.py','test_targets':['tests/test_fail.py'],'flags':['-q']},r); assert fail['status']=='failed'
    bad=run_bounded_test_operation({'operation_type':'run_bounded_test','test_targets':['tests/test_ok.py;rm -rf /'],'flags':['-q']},r); assert bad['status']=='rejected'
    full=run_bounded_test_operation({'operation_type':'run_bounded_test','flags':['-q']},r); assert 'full_suite_rejected' in full['errors']

def test_preview_read_only_no_consumption(tmp_path):
    r=repo(tmp_path); p=pkg(r,[{'operation_type':'create_text_file','target_path':'docs/a.txt','content':'a'}]); before=sorted(x.relative_to(r).as_posix() for x in r.rglob('*'))
    pv=preview_practical_execution(p,workspace_root=r); after=sorted(x.relative_to(r).as_posix() for x in r.rglob('*'))
    assert pv['mutation_occurred'] is False and pv['tests_executed'] is False and before==after

def test_execute_requires_governance_and_scope_and_drift(tmp_path):
    r=repo(tmp_path); (r/'docs/a.txt').write_text('x',encoding='utf-8'); h=sha_file(r/'docs/a.txt')
    p=pkg(r,[{'operation_type':'append_text','target_path':'docs/a.txt','append_content':'y','before_state':{'sha256':h}}])
    assert exe(p,r,confirm=False)['execution_status']=='execution_confirmation_required'
    assert execute_practical_change_package(p, approval={'decision':'rejected'}, authorization=auth(p), admitted=True, confirm_execution=True, workspace_root=r)['execution_status']=='approval_required'
    assert exe(p,r,admitted=False)['execution_status']=='adapter_admission_required'
    assert exe(p,r,scope=['tests'])['execution_status']=='failed'
    (r/'docs/a.txt').write_text('drift',encoding='utf-8'); assert exe(p,r)['failure_classification']=='workspace_drift_detected'

def test_evidence_diff_verify_unexpected_and_completion_not_auto(tmp_path):
    r=repo(tmp_path); (r/'docs/a.txt').write_text('x',encoding='utf-8')
    p=pkg(r,[{'operation_type':'append_text','target_path':'docs/a.txt','append_content':'y','before_state':{'sha256':sha_file(r/'docs/a.txt')}}])
    e=exe(p,r); assert e['before_hashes'] and e['after_hashes']; assert 'docs/a.txt' in e['git_diff_summary']['changed_paths']
    v=verify_practical_repository_execution(p,e); assert v['verification_status']=='verified' and v['human_completion_accepted'] is False
    (r/'docs/z.txt').write_text('z',encoding='utf-8'); e2={**e,'unexpected_changes':['docs/z.txt']}; assert verify_practical_repository_execution(p,e2)['verification_status']=='unexpected_change_detected'

def test_inspect_resume_legacy_and_persistence(tmp_path):
    assert inspect_practical_state({})['practical_task_runner_status']=='not_initialized'
    r=repo(tmp_path); p=pkg(r,[{'operation_type':'create_text_file','target_path':'docs/a.txt','content':'a'}])
    st=inspect_practical_state({'package':p}); assert st['operation_count']==1 and st['next_governed_action']=='requires_approval'
    rs=resume_practical_state({'package':p}); assert rs['will_modify_repository'] is False and rs['decision']=='requires_approval'

def test_cli_build_validate_preview_execute_verify_result(tmp_path):
    r=repo(tmp_path); plan={'session_id':'s','confirmed_specification':spec(),'work_request':wr(),'workspace_root':str(r),'operations':[{'operation_type':'create_text_file','target_path':'docs/a.txt','content':'a'}]}
    (tmp_path/'plan.json').write_text(__import__('json').dumps(plan),encoding='utf-8')
    store=tmp_path/'store'; base=[sys.executable,'-m','cli.zero_engineering_work','--store-root',str(store),'--session-id','s']
    assert subprocess.run(base+['build-change-package',str(tmp_path/'plan.json')],text=True,capture_output=True).returncode==0
    for cmd in ['validate-change-package','change-package','preview','inspect','resume']:
        cp=subprocess.run(base+[cmd],text=True,capture_output=True); assert cp.returncode==0 and 'Traceback' not in cp.stderr
    # seed governance artifacts for practical execute
    import json
    p=json.loads((store/'s/work-entry/governed-change-package.json').read_text())
    (store/'s/work-entry/approval.json').write_text(canonical_json(approval(p))+'\n',encoding='utf-8')
    (store/'s/work-entry/authorization.json').write_text(canonical_json(auth(p))+'\n',encoding='utf-8')
    (store/'s/work-entry/adapter-admission.json').write_text(canonical_json({'admission_status':'admitted'})+'\n',encoding='utf-8')
    assert subprocess.run(base+['execute'],text=True,capture_output=True).returncode==8
    assert subprocess.run(base+['execute','--confirm-execution','--workspace-root',str(r)],text=True,capture_output=True).returncode==0
    assert subprocess.run(base+['verify'],text=True,capture_output=True).returncode==0
    assert subprocess.run([sys.executable,'-m','cli.zero_engineering_work','--format','human','--store-root',str(store),'--session-id','s','result'],text=True,capture_output=True).returncode==0

def test_e2e_exact_python_change_test_failure_unauthorized_replay(tmp_path):
    r=repo(tmp_path); (r/'app.py').write_text('def greet(name):\n    return "Hello " + name\n',encoding='utf-8'); (r/'tests/test_app.py').write_text('from app import greet\ndef test_greet():\n assert greet("A")=="Hello A"\n',encoding='utf-8')
    h=sha_file(r/'app.py'); p=pkg(r,[{'operation_type':'replace_text_exact','target_path':'app.py','old_text':'def greet(name):\n    return "Hello " + name\n','new_text':'def greet(name):\n    return f"Hello {name}"\n','expected_occurrence_count':1,'before_state':{'sha256':h}},{'operation_type':'run_bounded_test','target_path':'tests/test_app.py','test_targets':['tests/test_app.py']}])
    e=exe(p,r); assert e['execution_status']=='executed' and e['test_results'][0]['status']=='passed'; assert verify_practical_repository_execution(p,e)['completion_candidate'] is True
    assert exe(p,r,consumed='consumed')['execution_status']=='authorization_reuse_rejected'
    pbad=pkg(r,[{'operation_type':'append_text','target_path':'app.py','append_content':'x','before_state':{'sha256':sha_file(r/'app.py')}}]); assert exe(pbad,r,scope=['docs'])['execution_status']=='failed'
    (r/'tests/test_fail.py').write_text('def test_no():\n assert False\n',encoding='utf-8'); pf=pkg(r,[{'operation_type':'append_text','target_path':'docs/n.txt','append_content':'x','before_state':{'sha256':'none'}},{'operation_type':'run_bounded_test','target_path':'tests/test_fail.py','test_targets':['tests/test_fail.py']}], scope=['docs','tests','app.py'])
