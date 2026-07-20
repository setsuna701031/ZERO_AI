from __future__ import annotations
import json, subprocess, sys
from core.engineering.engineering_failure_analysis_validation import validate_failure_analysis
from core.engineering.engineering_repair_continuation_eligibility import evaluate_repair_continuation_eligibility
from core.engineering.engineering_repair_continuation_eligibility_validation import validate_repair_continuation_eligibility
from core.engineering.engineering_repair_continuation_cycle import create_repair_continuation_cycle
from core.engineering.engineering_repair_continuation_cycle_validation import validate_repair_continuation_cycle
from core.engineering.engineering_feedback_controller import build_feedback_bundle
from core.engineering.engineering_feedback_report_validation import validate_feedback_report
from core.engineering.engineering_feedback_persistence import persist_feedback_state, resume_feedback_state
from core.engineering.engineering_task_artifact_adapter_registry import default_registry
from core.engineering.engineering_completion_foundation import build_verification_result
from core.engineering.engineering_repair_candidate import build_engineering_repair_candidate
from core.engineering.engineering_repair_plan import build_engineering_repair_plan
from core.engineering.engineering_change_proposal import assemble_change_proposal
from core.engineering.engineering_runtime_continuation import build_runtime_continuation
from core.engineering.engineering_verification_plan import build_verification_plan
from core.engineering.engineering_verification_run import build_verification_run


def fixture():
    analysis={'schema':'zero.engineering.repository_analysis_report.v1','repository_analysis_report_id':'analysis-1','fingerprint':'a'*64,'repository_identity':'repo','task_identity':'task'}
    cand=build_engineering_repair_candidate(task_id='task', repository_identity='repo', analysis_identity='analysis-1', analysis_fingerprint='a'*64, requested_outcome='fix bounded defect', defect_classification='test_failure', defect_summary='bounded defect', evidence_references=[{'evidence_id':'e1','evidence_type':'test','source_artifact_identity':'x','source_fingerprint':'b'*64,'bounded_summary':'bounded'}], target_scope=['src/a.py'], prohibited_scope=['secrets'])
    plan=build_engineering_repair_plan(candidate=cand, ordered_operations=[{'operation_type':'replace_file','target_path':'src/a.py','rationale':'fix failed test','verification_expectation_ids':['exp1'],'expected_postcondition':'focused expectation repaired'}], verification_expectations=[{'expectation_id':'exp1','expectation_type':'focused_test_passed','description':'focused'}])
    proposal=assemble_change_proposal({'intent':{'task_id':'task','repository_identity':'repo'},'workspace_evidence':{'workspace_id':'w','workspace_execution_closure_id':'cl','upstream_execution_session_id':'sess'},'scope_policy':{'maximum_affected_files':1,'maximum_total_proposed_content_bytes':0},'operations':[],'contents':[]})
    execution={'result_id':'exec','fingerprint':'c'*64,'affected_target_paths':['src/a.py']}
    vplan=build_verification_plan(session={'task_id':'task','repository_identity':'repo','execution_session_id':'sess'}, proposal=proposal, repair_plan=plan, execution_result=execution)
    vr=build_verification_result(task_id='task',repository_identity='repo',proposal=proposal,repair_plan=plan,execution_result=execution,verification_status='failed',verification_expectation_results=[{'expectation_id':'exp1','expectation_type':'focused_test_passed','status':'failed','summary':'assertion failed','evidence_reference_ids':['ev1']}],evidence_references=[{'evidence_id':'ev1','source_artifact_identity':'run','source_fingerprint':'d'*64,'bounded_summary':'short'}])
    vrun=build_verification_run(plan=vplan, admission={'verification_admission_id':'adm','fingerprint':'e'*64}, run_status='failed', step_results=[{'step_id':vplan['verification_steps'][0]['step_id'],'status':'failed','bounded_stdout_summary':'assertion failed','bounded_stderr_summary':'none','exit_code':1,'evidence_reference_ids':['ev1']}], evidence_references=vr['evidence_references'])
    cont=build_runtime_continuation(session={'execution_session_id':'sess'}, execution_result=execution, verification_result=vr, verification_run=vrun)
    return dict(original_analysis=analysis, original_candidate=cand, original_repair_plan=plan, original_proposal=proposal, execution_result=execution, verification_plan=vplan, verification_run=vrun, verification_evidence=vr['evidence_references'], verification_result=vr, runtime_continuation=cont, parent_execution_session={'execution_session_id':'sess'})

def test_feedback_bundle_reaches_awaiting_human_approval_and_validates():
    b=build_feedback_bundle(**fixture())
    assert b['status']=='awaiting_human_approval'
    assert validate_failure_analysis(b['failure_analysis'], verification_result=fixture()['verification_result'], original_repair_plan=fixture()['original_repair_plan'], execution_result=fixture()['execution_result']).valid
    assert validate_repair_continuation_eligibility(b['eligibility'], failure_analysis=b['failure_analysis']).valid
    assert validate_repair_continuation_cycle(b['cycle'], failure_analysis=b['failure_analysis'], eligibility=b['eligibility']).valid
    assert validate_feedback_report(b['report']).valid
    assert b['proposal']['status']=='proposed'
    assert b['cycle']['awaiting_human_approval'] is True

def test_failure_analysis_rejects_passed_unknown_scope_and_authority_payload():
    f=fixture(); b=build_feedback_bundle(**f); a=dict(b['failure_analysis'])
    passed=dict(f['verification_result']); passed['verification_status']='passed'; passed['status']='passed'
    assert 'passed_verification_rejected' in validate_failure_analysis(a, verification_result=passed).errors
    bad=dict(a); bad['affected_target_paths']=['../x']
    assert not validate_failure_analysis(bad).valid
    bad2=dict(a); bad2['approval_granted']=True
    assert 'authority_granting_field' in validate_failure_analysis(bad2).errors

def test_eligibility_cycle_bound_terminal_manual_and_no_material_change():
    f=fixture(); b=build_feedback_bundle(**f); a=b['failure_analysis']
    e=evaluate_repair_continuation_eligibility(failure_analysis=a, verification_result=f['verification_result'], runtime_continuation=f['runtime_continuation'], task_history=[{'schema':'zero.engineering.repair_continuation_cycle.v1'}]*3)
    assert e['eligible'] is False and e['eligibility_status']=='cycle_limit_reached'
    e=evaluate_repair_continuation_eligibility(failure_analysis={**a,'repairability':'manual_only'}, verification_result=f['verification_result'], runtime_continuation=f['runtime_continuation'])
    assert e['eligible'] is False
    e=evaluate_repair_continuation_eligibility(failure_analysis=a, verification_result=f['verification_result'], runtime_continuation=f['runtime_continuation'], task_state={'lifecycle_state':'closed'})
    assert e['eligible'] is False
    e=evaluate_repair_continuation_eligibility(failure_analysis=a, verification_result=f['verification_result'], runtime_continuation=f['runtime_continuation'], material_repair_change=False)
    assert 'no_material_repair_change' in e['reason_codes']

def test_adapter_registry_contains_canonical_feedback_adapters():
    inv={x['phase']:x for x in default_registry().inventory()}
    for phase in ('failure_analysis','repair_continuation_eligibility','repair_continuation_cycle','feedback_report'):
        assert inv[phase]['validation_level']=='canonical_validator'

def test_persistence_resume_bounded_and_no_full_output_or_command():
    b=build_feedback_bundle(**fixture())
    state=persist_feedback_state(failure_analysis=b['failure_analysis'],eligibility=b['eligibility'],continuation_cycle=b['cycle'],candidate=b['candidate'],plan=b['plan'],proposal=b['proposal'],proposal_linkage=b['proposal_linkage'])
    s=json.dumps(state)
    assert 'stdout' not in s and 'stderr' not in s and 'command' not in s and 'secret' not in s
    resumed=resume_feedback_state(state)
    assert resumed['resume_count']==1
    assert resumed['cycle_number']==state['cycle_number']

def test_cli_strict_json_build_and_validate_report():
    b=build_feedback_bundle(**fixture())
    p=subprocess.run([sys.executable,'-m','cli.zero_engineering_feedback','validate-report'],input=json.dumps({'value':b['report']}),text=True,capture_output=True)
    assert p.returncode==0
    assert json.loads(p.stdout)['valid'] is True
    p=subprocess.run([sys.executable,'-m','cli.zero_engineering_feedback','execute'],input='{}',text=True,capture_output=True)
    assert p.returncode==2 and p.stdout=='' and p.stderr
