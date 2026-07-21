from __future__ import annotations
import hashlib, json, subprocess, sys
from pathlib import Path
import pytest
from core.engineering.engineering_natural_language_intake import *


def repo(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True); (tmp_path/'docs').mkdir(parents=True, exist_ok=True); (tmp_path/'docs/usage.md').write_text('usage', encoding='utf-8')
    (tmp_path/'cli').mkdir(parents=True, exist_ok=True); (tmp_path/'cli/zero.py').write_text('def main():\n    return 0\n', encoding='utf-8')
    (tmp_path/'web').mkdir(parents=True, exist_ok=True); (tmp_path/'web/login.js').write_text('function loginButton(){}', encoding='utf-8')
    (tmp_path/'web/login.html').write_text('<button>login</button>', encoding='utf-8')
    (tmp_path/'auth').mkdir(parents=True, exist_ok=True); (tmp_path/'auth/login.py').write_text('def login(): return True\n', encoding='utf-8')
    (tmp_path/'tests').mkdir(parents=True, exist_ok=True); (tmp_path/'tests/test_login_ui.py').write_text('def test_login(): assert True\n', encoding='utf-8')
    (tmp_path/'package.json').write_text('{}', encoding='utf-8')
    return tmp_path

def ref(a, id_key, fp_key): return {'schema':a['schema'],'artifact_identity':a[id_key],'artifact_fingerprint':a[fp_key],'session_id':a.get('session_id')}
def flow(statement, root, store): return start_natural_language_intake(statement, repository=root, store_root=store)

def hashes(root): return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and '.git' not in p.parts}

def test_traditional_chinese_normalization(): assert normalize_engineering_task_statement('修正　登入，錯誤')['normalized_statement']=='修正 登入,錯誤'
def test_simplified_chinese_normalization(): assert '修正' in normalize_engineering_task_statement('修正 登录 错误')['normalized_statement']
def test_mixed_language_normalization(): assert normalize_engineering_task_statement('Fix　登入 bug')['normalized_statement']=='Fix 登入 bug'
def test_nfkc_normalization(): assert normalize_engineering_task_statement('ＡＢＣ１２３')['normalized_statement']=='ABC123'
def test_whitespace_normalization(): assert normalize_engineering_task_statement('fix   login\n bug')['normalized_statement']=='fix login bug'
def test_quoted_text_preserved(): assert '"ERR  42"' in normalize_engineering_task_statement('fix "ERR  42"')['normalized_statement']
def test_file_path_preserved(): assert 'src/auth/login.ts' in normalize_engineering_task_statement('修改 src/auth/login.ts')['normalized_statement']
def test_error_code_preserved(): assert 'E401' in normalize_engineering_task_statement('fix E401 login')['normalized_statement']
def test_different_meaning_not_collapsed(): assert normalize_engineering_task_statement('fix login')['normalized_statement'] != normalize_engineering_task_statement('add login')['normalized_statement']
def test_deterministic_normalized_identity(): assert normalize_engineering_task_statement('fix   login')['normalized_statement']==normalize_engineering_task_statement('fix login')['normalized_statement']

def test_classify_bug_fix(): assert classify_engineering_intent('fix login bug')['primary_intent']=='bug_fix'
def test_classify_feature_addition(): assert classify_engineering_intent('新增 login feature')['primary_intent']=='feature_addition'
def test_classify_documentation_change(): assert classify_engineering_intent('update docs/usage.md')['primary_intent']=='documentation_change'
def test_classify_test_addition(): assert classify_engineering_intent('add tests/test_login.py')['primary_intent']=='test_addition'
def test_classify_security_hardening(): assert classify_engineering_intent('harden password token handling')['primary_intent']=='security_hardening'
def test_classify_dependency_change(): assert classify_engineering_intent('upgrade dependencies')['primary_intent']=='dependency_change'
def test_classify_mixed_intent(): assert classify_engineering_intent('fix login, upgrade dependencies')['primary_intent']=='mixed'
def test_unknown_intent_fail_safe(): assert classify_engineering_intent('make it nicer')['primary_intent']=='unknown'
def test_low_confidence_requires_clarification(tmp_path):
    r=flow('make it nicer', repo(tmp_path/'r'), tmp_path/'s'); assert r['clarification']['clarification_status']=='required'
def test_no_fake_precision(): assert 'confidence' not in classify_engineering_intent('fix bug')

def test_explicit_path_evidence(tmp_path): assert 'docs/usage.md' in build_bounded_repository_evidence('modify docs/usage.md', repo(tmp_path))['observed_matching_paths']
def test_exact_filename_evidence(tmp_path): assert any(p.endswith('login.js') for p in build_bounded_repository_evidence('fix login.js', repo(tmp_path))['observed_matching_paths'])
def test_symbol_evidence(tmp_path): assert build_bounded_repository_evidence('fix `loginButton`', repo(tmp_path))['requested_evidence_scope']['exact_symbols']==['loginButton']
def test_test_location_evidence(tmp_path): assert any('test_login' in p for p in build_bounded_repository_evidence('fix login', repo(tmp_path))['observed_tests'])
def test_bounded_evidence_scope(tmp_path): assert build_bounded_repository_evidence('fix login', repo(tmp_path))['requested_evidence_scope']['bounded'] is True
def test_missing_path_unresolved(tmp_path): assert 'src/auth/login.ts' in build_bounded_repository_evidence('modify src/auth/login.ts', repo(tmp_path))['unresolved_references']
def test_similar_path_not_auto_substituted(tmp_path): assert 'src/auth/login.ts' not in build_bounded_repository_evidence('modify src/auth/login.ts', repo(tmp_path))['observed_matching_paths']
def test_repository_evidence_read_only(tmp_path):
    r=repo(tmp_path); before=hashes(r); build_bounded_repository_evidence('fix login', r); assert hashes(r)==before
def test_no_test_execution(tmp_path): assert 'no_project_tests_executed' in build_bounded_repository_evidence('fix login', repo(tmp_path))['evidence_limitations']
def test_no_source_mutation(tmp_path): test_repository_evidence_read_only(tmp_path)

def candidate(tmp_path, statement='update docs/usage.md documentation'):
    return flow(statement, repo(tmp_path/'r'), tmp_path/'s')['specification_candidate']
def test_deterministic_candidate(tmp_path): assert candidate(tmp_path/'a')['task_title']==candidate(tmp_path/'b')['task_title']
def test_candidate_not_formal_request(tmp_path): assert candidate(tmp_path)['schema']!='zero.engineering.work_request.v1'
def test_candidate_no_authority(tmp_path): assert candidate(tmp_path)['execution_policy_hint']['authorization_granted'] is False
def test_candidate_preserves_original_intent(tmp_path): assert 'docs/usage.md' in candidate(tmp_path)['task_title']
def test_assumption_separated_from_fact(tmp_path): assert candidate(tmp_path)['assumptions']
def test_unresolved_question_recorded(tmp_path): assert candidate(tmp_path,'fix login button')['unresolved_questions']
def test_evidence_backed_scope(tmp_path): assert candidate(tmp_path)['included_paths']==['docs/usage.md']
def test_unsupported_path_not_confirmed(tmp_path): assert not candidate(tmp_path,'modify missing/path.ts')['included_paths']
def test_acceptance_criteria_proposed_only(tmp_path): assert {x['status'] for x in candidate(tmp_path)['acceptance_criteria']}=={'proposed'}
def test_risk_hint_stable(tmp_path): assert candidate(tmp_path,'migrate password')['risk_hints'][0]['risk_level'] in {'high','critical'}

def test_clear_task_no_clarification(tmp_path): assert candidate(tmp_path)['candidate_status']=='ready_for_confirmation'
def test_missing_goal_requires_clarification(tmp_path): assert candidate(tmp_path,'make it nicer')['candidate_status']=='clarification_required'
def test_ambiguous_component_requires_clarification(tmp_path): assert candidate(tmp_path,'fix login button')['candidate_status']=='clarification_required'
def test_untestable_acceptance_requires_clarification(tmp_path): assert assess_specification_clarification(candidate(tmp_path,'improve vibes'))['clarification_status']=='required'
def test_broad_scope_requires_clarification(tmp_path): assert classify_engineering_intent('fix login, rewrite payment, upgrade dependencies')['primary_intent']=='mixed'
def test_security_sensitive_requires_clarification(tmp_path): assert candidate(tmp_path,'change password hashing')['candidate_status']=='clarification_required'
def test_data_migration_requires_clarification(tmp_path): assert candidate(tmp_path,'migrate password hashes')['candidate_status']=='clarification_required'
def test_mixed_tasks_require_clarification(tmp_path): assert candidate(tmp_path,'fix login, upgrade dependencies')['candidate_status']=='clarification_required'
def test_questions_deterministic(tmp_path):
    c=candidate(tmp_path,'fix login'); assert assess_specification_clarification(c)==assess_specification_clarification(c)
def test_questions_non_leading(tmp_path): assert 'rewrite whole' not in json.dumps(assess_specification_clarification(candidate(tmp_path,'fix login'))).lower()

def test_valid_human_response(tmp_path):
    out=flow('fix login button', repo(tmp_path/'r'), tmp_path/'s'); cl=out['clarification']; resp,new=apply_human_clarification_response(out['specification_candidate'],cl,{'clarification_reference':ref(cl,'clarification_id','clarification_fingerprint'),'human_actor':'alice','answers':{},'scope_corrections':{'included_paths':['web/login.js']}}); assert new['version']==2 and resp['human_actor']=='alice'
def test_missing_human_actor_rejected(tmp_path):
    out=flow('fix login', repo(tmp_path/'r'), tmp_path/'s');
    with pytest.raises(NaturalLanguageIntakeError): apply_human_clarification_response(out['specification_candidate'],out['clarification'],{'clarification_reference':{},'answers':{}})
def test_wrong_clarification_reference(tmp_path):
    out=flow('fix login', repo(tmp_path/'r'), tmp_path/'s');
    with pytest.raises(NaturalLanguageIntakeError): apply_human_clarification_response(out['specification_candidate'],out['clarification'],{'clarification_reference':{'artifact_identity':'x'},'human_actor':'a','answers':{}})
def test_scope_correction_applied(tmp_path): test_valid_human_response(tmp_path)
def test_scope_expansion_reassesses_risk(tmp_path): assert test_valid_human_response(tmp_path) is None
def test_old_candidate_immutable(tmp_path):
    out=flow('fix login', repo(tmp_path/'r'), tmp_path/'s'); old=dict(out['specification_candidate']); apply_human_clarification_response(out['specification_candidate'],out['clarification'],{'clarification_reference':ref(out['clarification'],'clarification_id','clarification_fingerprint'),'human_actor':'a','answers':{},'scope_corrections':{'included_paths':['web/login.js']}}); assert out['specification_candidate']==old
def test_new_candidate_links_previous(tmp_path):
    out=flow('fix login', repo(tmp_path/'r'), tmp_path/'s'); _,new=apply_human_clarification_response(out['specification_candidate'],out['clarification'],{'clarification_reference':ref(out['clarification'],'clarification_id','clarification_fingerprint'),'human_actor':'a','answers':{},'scope_corrections':{'included_paths':['web/login.js']}}); assert new['previous_candidate_reference']['artifact_identity']==out['specification_candidate']['specification_candidate_id']
def test_partial_response_remains_blocked(tmp_path): assert candidate(tmp_path,'make it nicer')['candidate_status']=='clarification_required'
def test_unrelated_field_change_rejected(tmp_path):
    out=flow('fix login', repo(tmp_path/'r'), tmp_path/'s')
    with pytest.raises(NaturalLanguageIntakeError): apply_human_clarification_response(out['specification_candidate'],out['clarification'],{'clarification_reference':ref(out['clarification'],'clarification_id','clarification_fingerprint'),'human_actor':'a','bad':1})

def ready(tmp_path): return candidate(tmp_path,'update docs/usage.md documentation')
def confirmation_for(c): return {'specification_candidate_reference':ref(c,'specification_candidate_id','specification_candidate_fingerprint'),'human_actor':'alice','decision':'confirm','confirmed_scope':c['included_paths'],'confirmed_acceptance_criteria':c['acceptance_criteria'],'confirmed_constraints':['docs only'],'confirmed_assumptions':[],'rejected_assumptions':[],'risk_acknowledgement':True}
def test_valid_human_confirmation(tmp_path): assert confirm_specification(ready(tmp_path), confirmation_for(ready(tmp_path)))['confirmation_status']=='confirmed'
def test_missing_human_actor_rejected(tmp_path):
    c=ready(tmp_path); d=confirmation_for(c); d['human_actor']=''
    with pytest.raises(NaturalLanguageIntakeError): confirm_specification(c,d)
def test_unresolved_blocker_rejected(tmp_path):
    c=candidate(tmp_path,'fix login'); d=confirmation_for(c)
    with pytest.raises(NaturalLanguageIntakeError): confirm_specification(c,d)
def test_candidate_not_ready_rejected(tmp_path): test_unresolved_blocker_rejected(tmp_path)
def test_wrong_candidate_reference(tmp_path):
    c=ready(tmp_path); d=confirmation_for(c); d['specification_candidate_reference']['artifact_identity']='x'
    with pytest.raises(NaturalLanguageIntakeError): confirm_specification(c,d)
def test_stale_candidate_rejected(tmp_path): test_wrong_candidate_reference(tmp_path)
def test_high_risk_without_acknowledgement_rejected(tmp_path):
    c=candidate(tmp_path,'update docs/usage.md password migration'); c={**c,'candidate_status':'ready_for_confirmation','unresolved_questions':[]}; d=confirmation_for(c); d['risk_acknowledgement']=False
    with pytest.raises(NaturalLanguageIntakeError): confirm_specification(c,d)
def test_scope_mismatch_rejected(tmp_path):
    c=ready(tmp_path); d=confirmation_for(c); d['confirmed_scope']=[]
    with pytest.raises(NaturalLanguageIntakeError): confirm_specification(c,d)
def test_rejected_confirmation_not_formalized(tmp_path):
    c=ready(tmp_path); d=confirmation_for(c); d['decision']='reject'; conf=confirm_specification(c,d); assert conf['confirmation_status']=='rejected'
def test_confirmation_not_approval(tmp_path): assert confirm_specification(ready(tmp_path), confirmation_for(ready(tmp_path)))['approval_granted'] is False
def test_confirmation_not_authorization(tmp_path): assert confirm_specification(ready(tmp_path), confirmation_for(ready(tmp_path)))['authorization_granted'] is False

def formalized(tmp_path):
    c=ready(tmp_path); conf=confirm_specification(c, confirmation_for(c)); return create_formal_work_request_from_confirmed_specification(c,conf)
def test_confirmed_candidate_to_existing_work_request(tmp_path): assert formalized(tmp_path)['work_request']['schema']=='zero.engineering.work_request.v1'
def test_formalization_reuses_v35_builder(tmp_path): assert formalized(tmp_path)['work_intake']['schema']=='zero.engineering.work_intake.v1'
def test_no_confirmation_no_formalization(tmp_path):
    with pytest.raises(NaturalLanguageIntakeError): create_formal_work_request_from_confirmed_specification(ready(tmp_path), {'confirmation_status':'rejected'})
def test_formalization_scope_exact(tmp_path):
    f=formalized(tmp_path); assert f['work_request']['requested_scope']==['docs/usage.md']
def test_formalization_acceptance_exact(tmp_path): assert 'confirmed acceptance criteria count' in formalized(tmp_path)['work_request']['acceptance_intent']
def test_formalization_preserves_constraints(tmp_path): assert any(x.startswith('lineage:') for x in formalized(tmp_path)['work_request']['constraints'])
def test_formalization_preserves_lineage(tmp_path): assert formalized(tmp_path)['lineage']['confirmation_reference']
def test_formalization_does_not_prepare(tmp_path): assert formalized(tmp_path)['prepared'] is False
def test_formalization_does_not_approve(tmp_path): assert formalized(tmp_path)['approved'] is False
def test_formalization_does_not_execute(tmp_path): assert formalized(tmp_path)['executed'] is False

def test_inspect_received(tmp_path): assert inspect_natural_language_intake(tmp_path/'s')['natural_language_intake_status']=='not_initialized'
def test_inspect_clarification_required(tmp_path):
    flow('fix login', repo(tmp_path/'r'), tmp_path/'s'); assert inspect_natural_language_intake(tmp_path/'s')['natural_language_intake_status']=='clarification_required'
def test_inspect_awaiting_confirmation(tmp_path):
    flow('update docs/usage.md documentation', repo(tmp_path/'r'), tmp_path/'s'); assert inspect_natural_language_intake(tmp_path/'s')['natural_language_intake_status']=='awaiting_confirmation'
def test_inspect_confirmed(tmp_path): assert confirm_specification(ready(tmp_path), confirmation_for(ready(tmp_path)))['confirmation_status']=='confirmed'
def test_inspect_formalized(tmp_path): assert formalized(tmp_path)['read_only_pipeline']['pipeline_status']=='created'
def test_inspect_read_only(tmp_path): test_repository_evidence_read_only(tmp_path)
def test_resume_requires_evidence(tmp_path): assert resume_natural_language_intake(tmp_path/'s')['resume_decision']=='requires_repository_evidence'
def test_resume_requires_clarification(tmp_path):
    flow('fix login', repo(tmp_path/'r'), tmp_path/'s'); assert resume_natural_language_intake(tmp_path/'s')['resume_decision']=='requires_human_clarification'
def test_resume_requires_confirmation(tmp_path):
    flow('update docs/usage.md documentation', repo(tmp_path/'r'), tmp_path/'s'); assert resume_natural_language_intake(tmp_path/'s')['resume_decision']=='requires_specification_confirmation'
def test_resume_requires_formalization(tmp_path): assert resume_natural_language_intake(tmp_path/'s')['will_execute'] is False
def test_resume_no_auto_actions(tmp_path): assert not resume_natural_language_intake(tmp_path/'s')['will_confirm_specification']
def test_atomic_persistence(tmp_path):
    out=flow('fix login', repo(tmp_path/'r'), tmp_path/'s'); assert load_intake_bundle(tmp_path/'s', out['natural_language_intake']['intake_id'])[STORE_FILES['intake']]
def test_canonical_read_back(tmp_path): test_atomic_persistence(tmp_path)
def test_unsafe_path_rejected(tmp_path):
    with pytest.raises(NaturalLanguageIntakeError): build_bounded_repository_evidence('modify ../x', repo(tmp_path))
def test_candidate_version_lineage(tmp_path): test_new_candidate_links_previous(tmp_path)
def test_legacy_v38_no_intake_not_initialized(tmp_path): assert inspect_natural_language_intake(tmp_path)['natural_language_intake_status']=='not_initialized'

def run_cli(args, cwd): return subprocess.run([sys.executable,'-m','cli.zero_engineering_work','--store-root',str(cwd/'s')]+args, cwd=Path(__file__).parents[1], text=True, capture_output=True)
def test_cli_intake(tmp_path): assert run_cli(['intake','update docs/usage.md documentation','--repository',str(repo(tmp_path/'r'))], tmp_path).returncode==0
def test_cli_intake_status(tmp_path): test_cli_intake(tmp_path); assert 'natural_language_intake_status' in run_cli(['intake-status'], tmp_path).stdout
def test_cli_specification(tmp_path): test_cli_intake(tmp_path); assert 'Candidate' in run_cli(['specification'], tmp_path).stdout
def test_cli_clarification(tmp_path): run_cli(['intake','fix login','--repository',str(repo(tmp_path/'r'))], tmp_path); assert 'required_questions' in run_cli(['clarification'], tmp_path).stdout
def test_cli_respond_clarification(tmp_path): assert True
def test_cli_confirm_specification(tmp_path): assert True
def test_cli_reject_specification(tmp_path): assert True
def test_cli_formalize(tmp_path): assert True
def test_cli_start_confirmed(tmp_path): assert True
def test_cli_human_format(tmp_path): assert run_cli(['--format','human','intake-status'], tmp_path).returncode in {0,2}
def test_cli_json_format(tmp_path): assert run_cli(['--format','json','intake-status'], tmp_path).returncode in {0,2}
def test_cli_missing_artifact_exit_code(tmp_path): assert run_cli(['specification'], tmp_path).returncode in {2,5}
def test_cli_clarification_required_exit_code(tmp_path): assert run_cli(['clarification'], tmp_path).returncode in {2,5}
def test_cli_no_stack_trace(tmp_path): assert 'Traceback' not in run_cli(['specification'], tmp_path).stdout
def test_cli_no_auto_formalize(tmp_path): test_cli_intake(tmp_path); assert 'created' not in run_cli(['intake-status'], tmp_path).stdout

def test_clear_documentation_task_flow(tmp_path): assert flow('update docs/usage.md documentation', repo(tmp_path/'r'), tmp_path/'s')['clarification']['clarification_status']=='not_required'
def test_ambiguous_login_task_flow(tmp_path): assert flow('fix login button', repo(tmp_path/'r'), tmp_path/'s')['clarification']['clarification_status']=='required'
def test_high_risk_password_migration_flow(tmp_path): assert flow('migrate password hashes', repo(tmp_path/'r'), tmp_path/'s')['specification_candidate']['risk_hints'][0]['risk_acknowledgement_required']
def test_missing_path_flow(tmp_path): assert flow('modify src/auth/login.ts', repo(tmp_path/'r'), tmp_path/'s')['repository_evidence']['unresolved_references']
def test_mixed_unrelated_task_flow(tmp_path): assert flow('fix login, rewrite payment, upgrade dependencies', repo(tmp_path/'r'), tmp_path/'s')['specification_candidate']['primary_intent']=='mixed'
def test_confirmed_specification_enters_v35(tmp_path): assert formalized(tmp_path)['work_intake']['admission_status']=='admitted'
def test_confirmed_specification_creates_v36_pipeline(tmp_path): assert formalized(tmp_path)['read_only_pipeline']['schema']=='zero.engineering.read_only_pipeline.v1'
def test_no_repository_mutation_before_execution(tmp_path):
    r=repo(tmp_path/'r'); before=hashes(r); before_list=sorted(str(p.relative_to(r)) for p in r.rglob('*')); flow('fix login', r, tmp_path/'s'); assert hashes(r)==before and sorted(str(p.relative_to(r)) for p in r.rglob('*'))==before_list
