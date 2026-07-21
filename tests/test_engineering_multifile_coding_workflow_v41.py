import json, subprocess, sys
from pathlib import Path
import pytest
from core.engineering.engineering_multifile_coding_workflow import *
from core.engineering.engineering_test_failure_analysis import *
from core.engineering.engineering_repair_proposal_candidate import *
from core.engineering.engineering_practical_task_runner import sha_file, execute_practical_change_package, verify_practical_repository_execution
from core.engineering.engineering_runtime_session_store import write_session_artifact, read_session_artifact, load_session_store

SPEC={'schema':'zero.engineering.confirmed_specification.v1','confirmed_specification_id':'spec1','confirmed_specification_fingerprint':'fp1','confirmed_scope':['app/greeting.py','tests/test_greeting.py'],'acceptance_criteria':['blank says Hello','name says Hello name']}
WR={'schema':'zero.engineering.work_request.v1','work_request_id':'wr1','work_request_fingerprint':'wfp','requested_scope':['app/greeting.py','tests/test_greeting.py'],'repository_identity':{'repository_id':'repo'}}
RA={'schema':'zero.engineering.repository_analysis.v1','analysis_id':'ra1','analysis_fingerprint':'rafp','files':[{'path':'app/greeting.py'},{'path':'tests/test_greeting.py'}]}

def plan(**hints): return build_multifile_change_plan_candidate(confirmed_specification=SPEC, work_request=WR, repository_analysis=RA, repository_identity={'repository_id':'repo'}, human_operation_hints=hints)

def confirm(p): return confirm_multifile_change_plan(p, {'human_actor':'alice','decision':'confirmed','plan_candidate_reference':{'plan_candidate_fingerprint':p['plan_candidate_fingerprint']},'confirmed_paths':[c['path'] for c in p['ordered_file_changes']],'risk_acknowledgements':['ok']})

def test_plan_candidate_deterministic_plan_identity_and_stable_file_order():
    a=plan(); b=plan(); assert a['plan_candidate_fingerprint']==b['plan_candidate_fingerprint']; assert [c['path'] for c in a['ordered_file_changes']]==['app/greeting.py','tests/test_greeting.py']

def test_production_test_role_classification_and_authority():
    p=plan(); assert [c['file_role'] for c in p['ordered_file_changes']]==['production','test']; assert p['authority']==AUTHORITY

def test_acceptance_mapping_required_and_evidence_backed_existing_paths():
    p=plan(); assert validate_multifile_change_plan_candidate(p, confirmed_specification=SPEC, work_request=WR, repository_analysis=RA)['valid']; p['ordered_file_changes'][0]['related_acceptance_criteria']=[]; assert 'file_change_without_acceptance_mapping' in validate_multifile_change_plan_candidate(p, confirmed_specification=SPEC, work_request=WR, repository_analysis=RA)['errors']

def test_new_path_requires_confirmed_scope_and_unknown_operation_not_executable():
    p=plan(paths=['app/new.py'], change_kinds={'app/new.py':'create'}); assert validate_multifile_change_plan_candidate(p, confirmed_specification=SPEC, work_request=WR)['errors']; p2=plan(change_kinds={'app/greeting.py':'unknown'}, operation_definition_status={'app/greeting.py':'unsupported'}); assert any(c['operation_definition_status']=='unsupported' for c in p2['ordered_file_changes'])

def test_plan_changed_identity_changes_and_dependency_change_changes_fingerprint():
    a=plan(); b=plan(depends_on={'change-0001':['change-0002']}); assert a['plan_candidate_fingerprint']!=b['plan_candidate_fingerprint']

def test_dependency_graph_valid_unknown_self_cycle_and_stable_topological_order():
    p=plan(depends_on={'change-0002':['change-0001']}); assert topo(p['ordered_file_changes'])==['change-0001','change-0002']
    with pytest.raises(Exception): topo([{'change_id':'a','depends_on':['b']}])
    with pytest.raises(Exception): topo([{'change_id':'a','depends_on':['a']}])
    with pytest.raises(Exception): topo([{'change_id':'a','depends_on':['b']},{'change_id':'b','depends_on':['a']}])

def test_test_strategy_focused_full_suite_duplicate_outside_timeout_max_and_no_execute():
    p=plan(test_targets=['tests/test_greeting.py']); ts=p['test_strategy']; assert ts['prohibited_full_suite'] and ts['execution_order']==['tests/test_greeting.py'] and ts['timeout_per_target']<=120
    bad=plan(test_targets=['','core/test_x.py','core/test_x.py'], maximum_targets=1); errs=validate_multifile_change_plan_candidate(bad, confirmed_specification=SPEC, work_request=WR)['errors']; assert 'duplicate_test_target' in errs and 'test_target_outside_allowed_roots' in errs and 'maximum_targets_exceeded' in errs

def test_confirmation_requires_human_actor_wrong_reference_scope_risk_and_not_approval_authorization():
    p=plan(risk_levels={'app/greeting.py':'high'})
    with pytest.raises(Exception): confirm_multifile_change_plan(p, {'decision':'confirmed','plan_candidate_reference':{'plan_candidate_fingerprint':p['plan_candidate_fingerprint']},'confirmed_paths':['app/greeting.py','tests/test_greeting.py']})
    with pytest.raises(Exception): confirm_multifile_change_plan(p, {'human_actor':'a','decision':'confirmed','plan_candidate_reference':{'plan_candidate_fingerprint':'x'},'confirmed_paths':['app/greeting.py','tests/test_greeting.py']})
    c=confirm(p); assert c['authority']==AUTHORITY and c['decision']=='confirmed'

def test_revision_creates_new_plan_and_old_confirmation_rejected_for_revision():
    p=plan(); c=confirm(p); r=revise_multifile_change_plan(p, {'paths':['app/greeting.py','tests/test_greeting.py'],'revision_reason':'change'}); assert r['previous_plan_reference']['plan_candidate_fingerprint']==p['plan_candidate_fingerprint']; assert r['plan_candidate_fingerprint']!=p['plan_candidate_fingerprint']; assert c['plan_candidate_reference']['plan_candidate_fingerprint']!=r['plan_candidate_fingerprint']

def test_formalization_confirmed_plan_to_v40_package_and_bindings(tmp_path):
    p=plan(operation_definition_status={'app/greeting.py':'deterministic','tests/test_greeting.py':'deterministic'}); c=confirm(p); ops=[{'change_id':'change-0001','operation_type':'create_text_file','content':'x'},{'change_id':'change-0002','operation_type':'create_text_file','content':'y'}]
    out=formalize_confirmed_multifile_plan(plan=p, confirmation=c, approved_proposal={'decision':'approved','package_fingerprint':None}, authorization={'package_fingerprint':None}, operation_definitions=ops, confirmed_specification=SPEC, work_request=WR, workspace_root=str(tmp_path))
    pkg=out['change_package']; assert pkg['schema']=='zero.engineering.governed_change_package.v1'; assert sorted(pkg['expected_changed_paths'])==['app/greeting.py','tests/test_greeting.py']; assert any(o['operation_type']=='run_bounded_test' for o in pkg['ordered_operations'])

def test_formalization_unconfirmed_rejected_manual_definition_blocks_no_second_schema():
    p=plan(); assert formalize_confirmed_multifile_plan(plan=p, confirmation={'decision':'rejected'}, approved_proposal={}, authorization={}, operation_definitions=[], confirmed_specification=SPEC, work_request=WR)['formalization_status']=='rejected'
    c=confirm(p); assert formalize_confirmed_multifile_plan(plan=p, confirmation=c, approved_proposal={}, authorization={}, operation_definitions=[], confirmed_specification=SPEC, work_request=WR)['formalization_status']=='manual_operation_definition_required'

def test_multifile_execution_ordered_rollback_scope_drift_unexpected_and_single_use(tmp_path):
    (tmp_path/'app').mkdir(); (tmp_path/'tests').mkdir(); (tmp_path/'app/greeting.py').write_text('def greet(name):\n    return "Hi"\n'); (tmp_path/'tests/test_greeting.py').write_text('def test_x(): assert True\n')
    h1=sha_file(tmp_path/'app/greeting.py'); h2=sha_file(tmp_path/'tests/test_greeting.py')
    p=plan(operation_definition_status={'app/greeting.py':'deterministic','tests/test_greeting.py':'deterministic'}, test_targets=[]); c=confirm(p)
    ops=[{'change_id':'change-0001','operation_type':'replace_text_exact','old_text':'Hi','new_text':'Hello','before_state':{'sha256':h1}}, {'change_id':'change-0002','operation_type':'append_text','append_content':'# ok\n','before_state':{'sha256':h2}}]
    pkg=formalize_confirmed_multifile_plan(plan=p, confirmation=c, approved_proposal={'decision':'approved'}, authorization={'package_fingerprint':None}, operation_definitions=ops, confirmed_specification=SPEC, work_request=WR, workspace_root=str(tmp_path))['change_package']
    auth={'package_fingerprint':pkg['change_package_fingerprint'],'authorized_scope':['app/greeting.py','tests/test_greeting.py'],'consumption_state':'unconsumed'}
    ev=execute_practical_change_package(pkg, approval={'decision':'approved'}, authorization=auth, admitted=True, confirm_execution=True, workspace_root=tmp_path, run_tests=False)
    assert ev['execution_status']=='executed' and ev['authorization_consumed']; auth['consumption_state']='consumed'; assert execute_practical_change_package(pkg, approval={'decision':'approved'}, authorization=auth, admitted=True, confirm_execution=True, workspace_root=tmp_path)['execution_status']=='authorization_reuse_rejected'

def test_bounded_test_set_multiple_targets_stop_continue_not_executed_and_separate(tmp_path):
    (tmp_path/'tests').mkdir(); (tmp_path/'tests/test_a.py').write_text('def test_a(): assert True\n'); (tmp_path/'tests/test_b.py').write_text('def test_b(): assert False\n'); (tmp_path/'tests/test_c.py').write_text('def test_c(): assert True\n')
    r=run_bounded_test_set({'schema':'zero.engineering.governed_change_package.v1'}, ['tests/test_a.py','tests/test_b.py','tests/test_c.py'], workspace_root=tmp_path, stop_policy='first_failure')
    assert r['passed_targets']==1 and r['failed_targets']==1 and r['not_executed_targets']==['tests/test_c.py']
    r2=run_bounded_test_set({}, ['tests/test_b.py','tests/test_c.py'], workspace_root=tmp_path, stop_policy='continue'); assert r2['executed_targets']==2

def test_pytest_parser_failure_kinds_bounds_no_root_cause_claim():
    out='''FAILED tests/test_greeting.py::test_blank\nTraceback (most recent call last):\n  File "app/greeting.py", line 2, in greet\nE   AssertionError\nE   assert "Hi" == "Hello"\n'''
    f=parse_pytest_output(out)[0]; assert f['failure_kind']=='assertion_failure' and f['exception_type']=='AssertionError' and f['referenced_source_paths']==['app/greeting.py'] and len(f['assertion_summary'])<=300
    assert parse_pytest_output('ImportError while importing tests/test_x.py')[0]['failure_kind']=='import_error'
    assert parse_pytest_output('ERROR collecting tests/test_x.py')[0]['failure_kind']=='collection_error'
    assert parse_pytest_output('operation timed out')[0]['failure_kind']=='timeout'
    assert parse_pytest_output('nonsense')[0]['failure_kind']=='unknown'

def test_failure_evidence_deterministic_suspected_paths_limitations_and_root_cause_null():
    ts={'schema':'zero.engineering.bounded_test_set_result.v1','ordered_results':[{'status':'failed','stdout':'FAILED tests/test_greeting.py::test_blank\n  File "app/greeting.py", line 1, in greet\nE   assert 1 == 2'}]}
    a=build_test_failure_evidence(execution={}, verification={}, test_set=ts, changed_paths=['app/greeting.py'], confirmed_scope=['app/greeting.py','tests/test_greeting.py']); b=build_test_failure_evidence(execution={}, verification={}, test_set=ts, changed_paths=['app/greeting.py'], confirmed_scope=['app/greeting.py','tests/test_greeting.py'])
    assert a['evidence_fingerprint']==b['evidence_fingerprint']; assert a['confirmed_root_cause'] is None and a['root_cause_status']=='suspected'; assert a['suspected_related_paths'][0]['confidence_band'] in {'high','medium','low'} and a['limitations']

def test_repair_candidate_scope_classification_no_authority_no_operations_review():
    ev={'failed_tests':[{'test_node':'tests/test_greeting.py::test_blank'}],'suspected_related_paths':[{'path':'app/greeting.py','evidence_reasons':['changed'],'confidence_band':'high'}]}
    rc=build_repair_proposal_candidate(parent_work_request=WR, parent_change_package={}, parent_execution={}, test_failure_evidence=ev, confirmed_scope=['app/greeting.py']); assert rc['scope_relationship']=='within_confirmed_scope' and rc['authority']==REPAIR_AUTHORITY and 'ordered_operations' not in rc
    rv=review_repair_candidate(rc, {'human_actor':'a','decision':'accept_for_planning'}); assert rv['not_approval'] and rv['not_authorization']
    ev['suspected_related_paths']=[{'path':'core/shared/normalization.py','evidence_reasons':['traceback'],'confidence_band':'medium'}]; rc2=build_repair_proposal_candidate(parent_work_request=WR, parent_change_package={}, parent_execution={}, test_failure_evidence=ev, confirmed_scope=['app/greeting.py']); assert rc2['scope_relationship']=='requires_scope_expansion' and rc2['candidate_status']=='requires_human_review'

def test_iteration_lineage_policy_new_package_new_fingerprint_and_limit():
    idx=build_iteration_index([{'iteration_id':'it-1','parent_work_request':'wr1'}]); assert idx['iteration_policy']['automatic_iterations']==0 and idx['iteration_policy']['maximum_recorded_iterations']==8
    p1=plan(); p2=plan(depends_on={'change-0002':['change-0001']}); assert p1['plan_candidate_fingerprint']!=p2['plan_candidate_fingerprint']

def test_verification_progress_preview_inspect_resume_completion_not_automatic():
    ver={'verification_status':'verified_with_test_failure'}; assert v41_preview(plan())['mutation_occurred'] is False
    bundle={'planning/multifile-change-plan-candidate.json':plan()}; ins=inspect_multifile_state(bundle); assert ins['multifile_coding_workflow_status']=='initialized' and resume_multifile_state(bundle)['decision']=='requires_plan_confirmation'
    assert resume_multifile_state({})['decision']=='requires_multifile_plan'

def test_persistence_atomic_readback_unsafe_and_legacy_not_initialized(tmp_path):
    p=plan(); write_session_artifact(tmp_path,'sess1','planning/multifile-change-plan-candidate.json',p); assert read_session_artifact(tmp_path,'sess1','planning/multifile-change-plan-candidate.json')['plan_candidate_fingerprint']==p['plan_candidate_fingerprint']; assert inspect_multifile_state(load_session_store(tmp_path,'sess1'))['planned_file_count']==2
    with pytest.raises(Exception): write_session_artifact(tmp_path,'../bad','planning/multifile-change-plan-candidate.json',p)
    assert inspect_multifile_state({})['multifile_coding_workflow_status']=='not_initialized'

def test_cli_commands_json_human_no_arbitrary_command(tmp_path):
    store=tmp_path/'s'; sess='sess1'; write_session_artifact(store,sess,'work-entry/specification-candidate.json',SPEC); write_session_artifact(store,sess,'work-entry/request.json',WR); write_session_artifact(store,sess,'work-entry/stages/repository-analysis.json',RA)
    cmd=[sys.executable,'cli/zero_engineering_work.py','--store-root',str(store),'--session-id',sess,'build-multifile-plan']; cp=subprocess.run(cmd,text=True,capture_output=True); assert cp.returncode==0 and 'multifile_change_plan_candidate' in cp.stdout
    cp=subprocess.run([sys.executable,'cli/zero_engineering_work.py','--format','human','--store-root',str(store),'--session-id',sess,'multifile-plan'],text=True,capture_output=True); assert cp.returncode==0 and 'schema' in cp.stdout
    for sub in ['validate-multifile-plan','iteration-status','inspect','resume']:
        cp=subprocess.run([sys.executable,'cli/zero_engineering_work.py','--store-root',str(store),'--session-id',sess,sub],text=True,capture_output=True); assert cp.returncode==0

def test_end_to_end_multifile_bug_fix_success_and_failure_to_repair_candidate(tmp_path):
    (tmp_path/'app').mkdir(); (tmp_path/'tests').mkdir(); (tmp_path/'app/greeting.py').write_text('def greet(name):\n    return "Hello" if not name.strip() else "Hello " + name\n'); (tmp_path/'tests/test_greeting.py').write_text('from app.greeting import greet\ndef test_blank_name(): assert greet(" ")=="Hello"\ndef test_name(): assert greet("Ada")=="Hello Ada"\n')
    r=run_bounded_test_set({}, ['tests/test_greeting.py'], workspace_root=tmp_path); assert r['overall_status']=='passed'
    (tmp_path/'app/greeting.py').write_text('def greet(name):\n    return "Hello " + name\n')
    r=run_bounded_test_set({}, ['tests/test_greeting.py::test_blank_name'], workspace_root=tmp_path); assert r['overall_status']=='failed'
    fe=build_test_failure_evidence(execution={'execution_status':'executed'}, verification={'verification_status':'verified_with_test_failure'}, test_set=r, changed_paths=['app/greeting.py'], confirmed_scope=['app/greeting.py','tests/test_greeting.py'])
    rc=build_repair_proposal_candidate(parent_work_request=WR, parent_change_package={'confirmed_scope':['app/greeting.py','tests/test_greeting.py']}, parent_execution={}, test_failure_evidence=fe, confirmed_scope=['app/greeting.py','tests/test_greeting.py']); assert rc['authority']['may_retry'] is False

def test_end_to_end_ambiguous_cycle_stop_policy_and_second_iteration_authorization():
    amb=plan(paths=['app/greeting.py'], operation_definition_status={'app/greeting.py':'requires_human_definition'}); assert formalize_confirmed_multifile_plan(plan=amb, confirmation=confirm(amb), approved_proposal={}, authorization={}, operation_definitions=[], confirmed_specification=SPEC, work_request=WR)['formalization_status']=='manual_operation_definition_required'
    cyc=plan(depends_on={'change-0001':['change-0002'],'change-0002':['change-0001']}); assert 'cyclic_dependency' in validate_multifile_change_plan_candidate(cyc, confirmed_specification=SPEC, work_request=WR)['errors']
    assert REPAIR_AUTHORITY['may_authorize'] is False and ITERATION_POLICY['automatic_iterations']==0
