from __future__ import annotations
import json, subprocess, sys, tempfile
from copy import deepcopy
from core.engineering.engineering_bootstrap_request import build_engineering_bootstrap_request
from core.engineering.engineering_bootstrap_request_validation import validate_engineering_bootstrap_request
from core.engineering.engineering_bootstrap_pipeline import bootstrap_engineering_task, validate_engineering_bootstrap_result
from core.engineering.engineering_task_orchestration import inspect_task
from core.engineering.engineering_task_artifact_adapter_registry import default_registry
from core.engineering.repository_analysis_report import build_repository_analysis_report
from tests.engineering_task_canonical_fixtures import structural


def req(**kw):
    base=dict(repository_identity='repo-1', repository_root_reference={'kind':'external_canonical_reference','id':'root-1'}, requested_outcome='Repair bounded contract mismatch', request_summary='Create analysis through proposal only.', target_scope=['a'], prohibited_scope=['secrets'], allowed_change_kinds=['replace_file'], verification_expectations=['file_exists'])
    base.update(kw)
    return build_engineering_bootstrap_request(**base)

def analysis(paths=('a',), evidence=True):
    def a(schema,status,id_key,prefix): return structural(schema,id_key,prefix,status)
    ar=a('zero.engineering.repository_analysis_request.v1','prepared','repository_analysis_request_id','engineering-repository-analysis-request')
    adm=a('zero.engineering.repository_root_admission.v1','admitted','repository_root_admission_id','engineering-root-admission')
    snap={**a('zero.engineering.repository_snapshot.v1','captured','repository_snapshot_id','engineering-repository-snapshot'),'entries':[],'truncated':False,'scoped_analysis_enabled':True,'normalized_scope':list(paths),'analyzed_paths':list(paths)}
    topo={**a('zero.engineering.repository_topology.v1','mapped','repository_topology_id','engineering-repository-topology'),'top_level_directories':[],'package_roots':[]}
    lang={**a('zero.engineering.repository_language_discovery.v1','discovered','repository_language_discovery_id','engineering-repository-language'),'languages':[],'primary_language_candidates':[]}
    build={**a('zero.engineering.repository_build_discovery.v1','discovered','repository_build_discovery_id','engineering-repository-build'),'detected_build_systems':[],'manifest_paths':[]}
    test={**a('zero.engineering.repository_test_discovery.v1','discovered','repository_test_discovery_id','engineering-repository-test'),'test_file_count':0,'framework_evidence':[]}
    dep={**a('zero.engineering.repository_dependency_analysis.v1','analyzed','repository_dependency_analysis_id','engineering-repository-dependency'),'python_import_edges':[]}
    inv={**a('zero.engineering.repository_engineering_inventory.v1','inventoried','repository_engineering_inventory_id','engineering-inventory'),'core_modules':[],'runtime_modules':[],'engineering_modules':[],'cli_modules':[],'test_modules':[]}
    ev={**a('zero.engineering.repository_analysis_evidence.v1','recorded','repository_analysis_evidence_id','engineering-repository-evidence'),'evidence_items':([{'evidence_id':'ev-1'}] if evidence else [])}
    return build_repository_analysis_report(ar,adm,snap,topo,lang,build,test,dep,inv,ev)

def test_bootstrap_request_deterministic_and_fail_closed():
    r=req(target_scope=['a','a'])
    assert r==req(target_scope=['a'])
    assert validate_engineering_bootstrap_request(r).valid
    for mut in [{'target_scope':['../x']},{'target_scope':['/x']},{'target_scope':['secrets/x']},{'allowed_change_kinds':['execute']},{'verification_expectations':['file_exists','file_exists']},{'authority_boundary':{'approval':'granted'}},{'note':'git status shell=True'},{'deterministic':False}]:
        bad=deepcopy(r); bad.update(mut)
        assert not validate_engineering_bootstrap_request(bad).valid

def test_bootstrap_pipeline_success_replay_and_boundaries(tmp_path):
    r=req(); a=analysis()
    out=bootstrap_engineering_task(repo_root=tmp_path, bootstrap_request=r, repository_analysis=a)
    assert out['bootstrap_status']=='proposal_ready'
    assert validate_engineering_bootstrap_result(out).valid
    state_path=next((tmp_path/'.zero'/'engineering'/'tasks').glob('engineering-task-*/state.json'))
    state=inspect_task(tmp_path, state_path.parent.name)
    assert state['lifecycle_state']=='awaiting_human_approval'
    assert not state['approval_identity'] and not state['authorization_identity'] and not state['authorization_token_identity']
    replay=bootstrap_engineering_task(repo_root=tmp_path, bootstrap_request=r, repository_analysis=a)
    assert replay==out

def test_bootstrap_blocks_insufficient_and_out_of_scope(tmp_path):
    assert bootstrap_engineering_task(repo_root=tmp_path/'one', bootstrap_request=req(), repository_analysis=analysis(evidence=False))['bootstrap_status']=='insufficient_evidence'
    assert bootstrap_engineering_task(repo_root=tmp_path/'two', bootstrap_request=req(), repository_analysis=analysis(paths=('b',)))['bootstrap_status']=='blocked'

def test_bootstrap_adapters_registered():
    reg=default_registry(); r=req(); out=bootstrap_engineering_task(repo_root=tempfile.TemporaryDirectory().name, bootstrap_request=r, repository_analysis=analysis())
    assert reg.validate_artifact('bootstrap_request', r)['validation_status']=='requested'
    assert reg.validate_artifact('bootstrap_result', out)['validation_status']=='proposal_ready'
    fake={**r,'schema':'zero.engineering.bootstrap_request.v2'}
    try: reg.validate_artifact('bootstrap_request', fake); ok=False
    except Exception: ok=True
    assert ok

def test_bootstrap_cli_strict_json(tmp_path):
    payload={'repository_identity':'repo-1','repository_root_reference':{'id':'root-1'},'requested_outcome':'Repair bounded contract mismatch','request_summary':'summary','target_scope':['a'],'prohibited_scope':['secrets'],'allowed_change_kinds':['replace_file'],'verification_expectations':['file_exists']}
    p=tmp_path/'r.json'; a=tmp_path/'a.json'; res=tmp_path/'res.json'
    built=subprocess.run([sys.executable,'-m','cli.zero_engineering_bootstrap','build-bootstrap-request','--json',json.dumps(payload)],text=True,capture_output=True,check=False)
    assert built.returncode==0 and json.loads(built.stdout)['schema']=='zero.engineering.bootstrap_request.v1'
    p.write_text(built.stdout,encoding='utf-8'); a.write_text(json.dumps(analysis()),encoding='utf-8')
    val=subprocess.run([sys.executable,'-m','cli.zero_engineering_bootstrap','validate-bootstrap-request','--request',str(p)],text=True,capture_output=True,check=False)
    assert val.returncode==0 and json.loads(val.stdout)['valid'] is True
    run=subprocess.run([sys.executable,'-m','cli.zero_engineering_bootstrap','run-bootstrap','--request',str(p),'--analysis-input',str(a),'--state-root',str(tmp_path/'state')],text=True,capture_output=True,check=False)
    assert run.returncode==0 and json.loads(run.stdout)['bootstrap_status']=='proposal_ready'
    res.write_text(run.stdout,encoding='utf-8')
    check=subprocess.run([sys.executable,'-m','cli.zero_engineering_bootstrap','validate-bootstrap-result','--result',str(res)],text=True,capture_output=True,check=False)
    assert check.returncode==0 and json.loads(check.stdout)['valid'] is True
