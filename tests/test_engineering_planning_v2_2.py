import json, subprocess, sys
import pytest
from core.engineering.engineering_repair_candidate import build_engineering_repair_candidate, SCHEMA as CANDIDATE_SCHEMA
from core.engineering.engineering_repair_candidate_validation import validate_engineering_repair_candidate
from core.engineering.engineering_repair_plan import build_engineering_repair_plan, SCHEMA as PLAN_SCHEMA
from core.engineering.engineering_repair_plan_validation import validate_engineering_repair_plan
from core.engineering.engineering_task_artifact_adapter_registry import default_registry
from core.engineering.engineering_task_artifact_compatibility import build_compatibility_report
from core.engineering.engineering_task_orchestration import create_task, admit_task, attach_analysis, attach_candidate_selection, attach_plan, attach_proposal, inspect_task
from tests import engineering_task_canonical_fixtures as cf


def candidate(**kw):
    base=dict(task_id='task-1', repository_identity='repo-1', analysis_identity='analysis-1', analysis_fingerprint='a'*64, requested_outcome='fix bounded defect', defect_classification='contract_mismatch', defect_summary='bounded defect', evidence_references=[{'evidence_id':'e1','evidence_type':'analysis','source_artifact_identity':'analysis-1','source_fingerprint':'a'*64,'repository_relative_path':'src/a.py','bounded_summary':'bounded evidence'}], target_scope=['src/a.py'], prohibited_scope=['secrets'])
    base.update(kw); return dict(build_engineering_repair_candidate(**base))

def plan(c=None, **kw):
    c=c or candidate()
    base=dict(candidate=c, ordered_operations=[{'operation_type':'replace_file','target_path':'src/a.py','rationale':'bounded rationale','expected_postcondition':'contract fixed','verification_expectation_ids':['v1']}], verification_expectations=[{'expectation_id':'v1','expectation_type':'focused_test_passed','target_path':'src/a.py','required':True,'expected_status':'passed','description':'focused test passes'}])
    base.update(kw); return dict(build_engineering_repair_plan(**base))

def test_candidate_deterministic_and_fail_closed():
    a=candidate(); b=candidate(evidence_references=list(reversed(a['evidence_references'])))
    assert a['candidate_id']==b['candidate_id'] and a['fingerprint']==b['fingerprint']
    assert candidate(analysis_identity='analysis-2')['candidate_id']!=a['candidate_id']
    assert candidate(target_scope=['src/b.py'])['fingerprint']!=a['fingerprint']
    assert validate_engineering_repair_candidate(a, task_id='task-1', repository_identity='repo-1', analysis_identity='analysis-1', analysis_fingerprint='a'*64, request_scope=['src']).valid
    bad={**a,'schema':'zero.test.fake.v1'}; assert not validate_engineering_repair_candidate(bad).valid
    bad={**a,'fingerprint':'0'*64}; assert not validate_engineering_repair_candidate(bad).valid
    bad={**a,'evidence_references':[]}; assert not validate_engineering_repair_candidate(bad).valid
    bad={**a,'target_scope':['/abs']}; assert not validate_engineering_repair_candidate(bad).valid
    bad={**a,'target_scope':['src/a.py'],'prohibited_scope':['src']}; assert not validate_engineering_repair_candidate(bad).valid
    bad={**a,'approval_granted':True}; assert not validate_engineering_repair_candidate(bad).valid
    assert a['authority_boundary']['mutation']=='not_granted'

def test_plan_deterministic_scope_and_fail_closed():
    c=candidate(); a=plan(c); b=plan(c)
    assert a['repair_plan_id']==b['repair_plan_id'] and a['fingerprint']==b['fingerprint']
    assert a['ordered_operations'][0]['sequence']==1
    assert plan(c, prohibited_target_paths=['secrets','private'])['fingerprint']!=a['fingerprint']
    assert validate_engineering_repair_plan(a, candidate=c, request_scope=['src']).valid
    for mut in [lambda x:{**x,'candidate_identity':'wrong'}, lambda x:{**x,'candidate_fingerprint':'0'*64}, lambda x:{**x,'ordered_operations':[],'operation_count':0}, lambda x:{**x,'plan_status':'blocked','status':'blocked'}, lambda x:{**x,'approval_granted':True}]:
        assert not validate_engineering_repair_plan(mut(a), candidate=c, request_scope=['src']).valid
    bad=plan(c, allowed_target_paths=['src/a.py'], ordered_operations=[{'operation_type':'replace_file','target_path':'src/b.py','rationale':'bounded rationale','expected_postcondition':'x','verification_expectation_ids':['v1']}])
    assert not validate_engineering_repair_plan(bad, candidate=c, request_scope=['src']).valid
    assert a['authority_boundary']['git']=='not_granted'

def test_adapters_and_orchestration(tmp_path):
    reg=default_registry()
    c=candidate(); p=plan(c)
    assert reg.lookup('candidate_selection', CANDIDATE_SCHEMA).descriptor.validation_level=='canonical_validator'
    assert reg.lookup('repair_plan', PLAN_SCHEMA).descriptor.validation_level=='canonical_validator'
    with pytest.raises(Exception): reg.validate_artifact('candidate_selection', {'schema':'zero.engineering.task_candidate_selection.v1','status':'selected'})
    report=build_compatibility_report(); phases={r['phase']:r for r in report['adapters']}
    assert phases['candidate_selection']['orchestration_readiness']=='ready'
    assert phases['repair_plan']['orchestration_readiness']=='ready'
    req={'repository_identity':'repo-1','requested_outcome':'fix bounded defect','bounded_target_scope':['src'],'prohibited_scope':['secrets']}
    s=create_task(tmp_path, req); tid=s['task_id']; admit_task(tmp_path,tid)
    analysis=cf.analysis_report(); c=candidate(task_id=tid, repository_identity='repo-1', analysis_identity=analysis['repository_analysis_report_id'], analysis_fingerprint=analysis['fingerprint'])
    with pytest.raises(Exception): attach_candidate_selection(tmp_path,tid,c)
    attach_analysis(tmp_path,tid,analysis); attach_candidate_selection(tmp_path,tid,c)
    assert attach_candidate_selection(tmp_path,tid,c)['lifecycle_state']=='candidate_selected'
    p=plan(c); attach_plan(tmp_path,tid,p)
    state=inspect_task(tmp_path,tid)
    assert state['candidate_identity']['artifact_fingerprint']==c['fingerprint'] and 'evidence_references' not in state['candidate_identity']
    with pytest.raises(Exception): attach_proposal(tmp_path,tid,{'schema':'zero.test.proposal.v1','status':'proposed'})

def test_cli_build_validate(tmp_path):
    payload=json.dumps({'task_id':'task-1','repository_identity':'repo-1','analysis_identity':'analysis-1','analysis_fingerprint':'a'*64,'requested_outcome':'fix bounded defect','defect_classification':'contract_mismatch','defect_summary':'bounded defect','evidence_references':[{'evidence_id':'e1','evidence_type':'analysis','source_artifact_identity':'analysis-1','source_fingerprint':'a'*64,'repository_relative_path':'src/a.py','bounded_summary':'bounded evidence'}],'target_scope':['src/a.py']})
    r=subprocess.run([sys.executable,'cli/zero_engineering_task.py','build-candidate','--json',payload],text=True,capture_output=True,check=False)
    assert r.returncode==0
    cand=json.loads(r.stdout)
    r=subprocess.run([sys.executable,'cli/zero_engineering_task.py','validate-candidate','--json',json.dumps({'candidate':cand,'request_scope':['src']})],text=True,capture_output=True,check=False)
    assert r.returncode==0 and json.loads(r.stdout)['valid'] is True
    bad=subprocess.run([sys.executable,'cli/zero_engineering_task.py','build-candidate','--json','{bad'],text=True,capture_output=True,check=False)
    assert bad.returncode==2
