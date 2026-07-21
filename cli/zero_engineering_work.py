from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.engineering.engineering_work_entry import *
from core.engineering.engineering_read_only_pipeline import create_read_only_pipeline, run_read_only_pipeline, run_next_read_only_stage, inspect_read_only_pipeline, resume_read_only_pipeline, verify_read_only_pipeline, ReadOnlyPipelineError
from core.engineering.engineering_runtime_orchestrator_common import canonical_json
from core.engineering.engineering_approval_execution_activation import *
from core.engineering.engineering_operator_flow import build_operator_status, start_operator_flow, prepare_operator_flow, create_demo_activation, preview_execution, human_text, resolve_active_engineering_work
from core.engineering.engineering_natural_language_intake import *
from core.engineering.engineering_runtime_session_store import write_session_artifact
from core.engineering.engineering_practical_task_runner import build_governed_change_package, validate_governed_change_package, preview_practical_execution, execute_practical_change_package, verify_practical_repository_execution, bounded_test_policy, practical_result, inspect_practical_state, resume_practical_state, run_bounded_test_operation
from core.engineering.engineering_multifile_coding_workflow import *
from core.engineering.engineering_test_failure_analysis import build_test_failure_evidence
from core.engineering.engineering_repair_proposal_candidate import build_repair_proposal_candidate, review_repair_candidate, build_iteration_index
from core.engineering.engineering_runtime_session_store import load_session_store

def _load(p):
    with open(p, encoding='utf-8') as f: return json.load(f)
def _dump(x): sys.stdout.write(canonical_json(x)+"\n")
def _emit(x, fmt, verbose=False): print(human_text(x, verbose=verbose) if fmt=='human' else canonical_json(x))
def _store(ns): return Path(ns.store_root or '.zero-engineering-sessions')
def _sid(ns): return getattr(ns,'session_id',None)


def _legacy_main(argv):
    lp=argparse.ArgumentParser()
    sub=lp.add_subparsers(dest='cmd', required=True)
    ss=sub.add_parser('submit'); ss.add_argument('--statement', required=True); ss.add_argument('--repo-id', required=True); ss.add_argument('--repo-root', default='.'); ss.add_argument('--scope', action='append', required=True); ss.add_argument('--mode', default='governed_delivery'); ss.add_argument('--acceptance-intent', default='human_review')
    for c in ('prepare','prepare-next','inspect','resume','human-gate','verify-pipeline'):
        x=sub.add_parser(c); x.add_argument('coordination_json'); x.add_argument('--request-json'); x.add_argument('--intake-json'); x.add_argument('--pipeline-json'); x.add_argument('--repo-root')
    for c in ('attach-approval','authorization-handoff','attach-authorization','prepare-execution','admit-adapter','execute','verify-execution','evaluate-progress','verify-activation'):
        x=sub.add_parser(c); x.add_argument('activation_json'); x.add_argument('--approval-json'); x.add_argument('--authorization-json'); x.add_argument('--handoff-json'); x.add_argument('--preparation-json'); x.add_argument('--admission-json'); x.add_argument('--execution-json'); x.add_argument('--verification-json'); x.add_argument('--workspace-root', default='.')
    ns=lp.parse_args(argv)
    try:
        if ns.cmd=='submit':
            r=create_engineering_work_request(request_statement=ns.statement,repository_identity={'repository_id':ns.repo_id},repository_root_reference=ns.repo_root,requested_scope=ns.scope,requested_mode=ns.mode,acceptance_intent=ns.acceptance_intent); i=admit_engineering_work(r); c=create_work_coordination(r,i); pl=create_read_only_pipeline(r,i,c); out={'work_request':r,'work_intake':i,'coordination':c,'read_only_pipeline':pl}
        elif ns.cmd in {'prepare','prepare-next'}:
            c=_load(ns.coordination_json); r=_load(ns.request_json); i=_load(ns.intake_json); pl=_load(ns.pipeline_json); out=run_next_read_only_stage(r,i,c,pl,repository_root=ns.repo_root) if ns.cmd=='prepare-next' else run_read_only_pipeline(r,i,c,pl,repository_root=ns.repo_root)
        elif ns.cmd=='inspect':
            c=_load(ns.coordination_json); pl=_load(ns.pipeline_json) if ns.pipeline_json else None; out={**inspect_work_coordination(c),'read_only_pipeline':inspect_read_only_pipeline(c,pl)}
        elif ns.cmd=='resume': out=resume_read_only_pipeline(_load(ns.coordination_json), _load(ns.pipeline_json) if ns.pipeline_json else None)
        elif ns.cmd=='verify-pipeline': out=verify_read_only_pipeline(_load(ns.pipeline_json))
        elif ns.cmd=='human-gate': out=create_human_gate_handoff(_load(ns.coordination_json))
        elif ns.cmd=='verify-activation': out=validate_activation(_load(ns.activation_json))
        elif ns.cmd=='attach-approval': out=attach_human_approval(_load(ns.activation_json), _load(ns.approval_json))
        elif ns.cmd=='authorization-handoff': out=create_authorization_handoff(_load(ns.activation_json), _load(ns.approval_json))
        elif ns.cmd=='attach-authorization': out=attach_human_authorization(_load(ns.activation_json), _load(ns.authorization_json), _load(ns.approval_json))
        elif ns.cmd=='prepare-execution': prep,act=prepare_execution(_load(ns.activation_json), _load(ns.authorization_json), workspace_root=ns.workspace_root); out={'execution_preparation':prep,'activation':act}
        elif ns.cmd=='admit-adapter': adm,act=admit_adapter(_load(ns.activation_json), _load(ns.preparation_json)); out={'adapter_admission':adm,'activation':act}
        elif ns.cmd=='execute': er,auth,act=activate_governed_execution(_load(ns.activation_json), _load(ns.authorization_json), _load(ns.preparation_json), _load(ns.admission_json), workspace_root=ns.workspace_root); out={'execution_result':er,'authorization':auth,'activation':act}
        elif ns.cmd=='verify-execution': ver,act=verify_execution(_load(ns.activation_json), _load(ns.execution_json)); out={'verification':ver,'activation':act}
        elif ns.cmd=='evaluate-progress': pr,act=evaluate_progress(_load(ns.activation_json), _load(ns.verification_json)); out={'progress':pr,'activation':act}
        _dump(out); return 0
    except (WorkEntryError, ReadOnlyPipelineError, ActivationError, NaturalLanguageIntakeError) as e:
        _dump({'valid':False,'error':e.code}); return 2

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in {'submit','prepare-next','human-gate','verify-pipeline','authorization-handoff','verify-execution','verify-activation'}:
        return _legacy_main(argv)
    if argv and argv[0] in {'inspect','resume','attach-approval','attach-authorization','prepare-execution','admit-adapter','execute','evaluate-progress'} and len(argv)>1 and argv[1].endswith('.json'):
        return _legacy_main(argv)
    p=argparse.ArgumentParser(prog='zero engineering')
    p.add_argument('--format', choices=['json','human'], default='json'); p.add_argument('--verbose', action='store_true'); p.add_argument('--store-root', default='.zero-engineering-sessions'); p.add_argument('--session-id')
    sub=p.add_subparsers(dest='cmd', required=True)
    s=sub.add_parser('start'); s.add_argument('statement'); s.add_argument('--repository', default='.'); s.add_argument('--repo-id', default='default'); s.add_argument('--scope', action='append', default=['docs/status.txt']); s.add_argument('--mode', default='governed_delivery'); s.add_argument('--acceptance-intent', default='ZERO engineering flow verified.'); s.add_argument('--prepare', action='store_true'); s.add_argument('--legacy-direct-work-request', action='store_true')
    for c in ('status','inspect','review','approval-summary','authorization-summary','preview','result','resume','completion-review-summary','verify-flow','intake-status','specification','clarification','formalize','start-confirmed','validate-change-package','change-package','execution-evidence','run-tests','build-multifile-plan','validate-multifile-plan','multifile-plan','test-failure-evidence','repair-candidate','iteration-status'):
        sub.add_parser(c)
    bcp=sub.add_parser('build-change-package'); bcp.add_argument('operations_json')
    ni=sub.add_parser('intake'); ni.add_argument('statement'); ni.add_argument('--repository', default='.'); ni.add_argument('--repo-id', default='default'); ni.add_argument('--mode', default='governed_delivery')
    rc=sub.add_parser('respond-clarification'); rc.add_argument('response_json')
    for name in ('confirm-multifile-plan','reject-multifile-plan','revise-multifile-plan','formalize-multifile-plan','review-repair-candidate'):
        sp=sub.add_parser(name); sp.add_argument('json_file', nargs='?')
    tsp=sub.add_parser('test-set'); tsp.add_argument('--execute', action='store_true')
    cc=sub.add_parser('confirm-specification'); cc.add_argument('confirmation_json')
    rj=sub.add_parser('reject-specification'); rj.add_argument('confirmation_json')
    sub.add_parser('prepare').add_argument('--repository', default='.')
    aa=sub.add_parser('attach-approval'); aa.add_argument('approval_json')
    ah=sub.add_parser('attach-authorization'); ah.add_argument('authorization_json'); ah.add_argument('--approval-json')
    pe=sub.add_parser('prepare-execution'); pe.add_argument('--authorization-json'); pe.add_argument('--workspace-root', default='.')
    ad=sub.add_parser('admit-adapter'); ad.add_argument('--preparation-json')
    ex=sub.add_parser('execute'); ex.add_argument('--confirm-execution', action='store_true'); ex.add_argument('--authorization-json'); ex.add_argument('--preparation-json'); ex.add_argument('--admission-json'); ex.add_argument('--workspace-root', default='.')
    ve=sub.add_parser('verify'); ve.add_argument('--execution-json')
    ep=sub.add_parser('evaluate-progress'); ep.add_argument('--verification-json')
    # legacy commands
    for c in ('submit','prepare-next','human-gate','verify-pipeline','authorization-handoff','verify-execution','verify-activation'):
        x=sub.add_parser(c); x.add_argument('jsons', nargs='*'); x.add_argument('--statement'); x.add_argument('--repo-id'); x.add_argument('--repo-root', default='.'); x.add_argument('--request-json'); x.add_argument('--intake-json'); x.add_argument('--pipeline-json'); x.add_argument('--approval-json'); x.add_argument('--authorization-json'); x.add_argument('--handoff-json'); x.add_argument('--preparation-json'); x.add_argument('--admission-json'); x.add_argument('--execution-json'); x.add_argument('--verification-json'); x.add_argument('--workspace-root', default='.')
    ns=p.parse_args(argv)
    try:
        if ns.cmd=='start':
            if ns.legacy_direct_work_request:
                out=start_operator_flow(ns.statement,store_root=_store(ns),repository=ns.repository,repo_id=ns.repo_id,scope=ns.scope,mode=ns.mode,acceptance_intent=ns.acceptance_intent,prepare=ns.prepare); out['governance_warning']='legacy direct Work Request path; not allowed for high-risk or unknown intent and still requires v3.5 validation'
            else:
                out=start_natural_language_intake(ns.statement,store_root=_store(ns),repository=ns.repository,repo_id=ns.repo_id,requested_mode=ns.mode)
        elif ns.cmd=='intake': out=start_natural_language_intake(ns.statement,store_root=_store(ns),repository=ns.repository,repo_id=ns.repo_id,requested_mode=ns.mode)
        elif ns.cmd=='intake-status': out=inspect_natural_language_intake(_store(ns), session_id=_sid(ns))
        elif ns.cmd=='specification':
            b=load_intake_bundle(_store(ns), _sid(ns)); out={'human_notice':'這是候選規格，尚未確認。Candidate is not a Work Request.', 'specification_candidate':b.get(STORE_FILES['candidate'])}
        elif ns.cmd=='clarification':
            b=load_intake_bundle(_store(ns), _sid(ns)); cl=b.get(STORE_FILES['clarification']); out={'clarification_status':(cl or {}).get('clarification_status'),'required_questions':(cl or {}).get('required_questions',[]),'optional_questions':(cl or {}).get('optional_questions',[]),'prohibited_assumptions':(cl or {}).get('prohibited_assumptions',[])}
        elif ns.cmd=='respond-clarification':
            b=load_intake_bundle(_store(ns), _sid(ns)); resp,new=apply_human_clarification_response(b[STORE_FILES['candidate']], b[STORE_FILES['clarification']], _load(ns.response_json)); sid=b[STORE_FILES['intake']]['intake_id']; write_session_artifact(_store(ns),sid,STORE_FILES['response'],resp); write_session_artifact(_store(ns),sid,STORE_FILES['candidate'],new); out={'clarification_response':resp,'specification_candidate':new}
        elif ns.cmd in {'confirm-specification','reject-specification'}:
            b=load_intake_bundle(_store(ns), _sid(ns)); raw=_load(ns.confirmation_json); raw['decision']='reject' if ns.cmd=='reject-specification' else raw.get('decision','confirm'); conf=confirm_specification(b[STORE_FILES['candidate']], raw); sid=b[STORE_FILES['intake']]['intake_id']; write_session_artifact(_store(ns),sid,STORE_FILES['confirmation'],conf); out={'specification_confirmation':conf}
        elif ns.cmd in {'formalize','start-confirmed'}:
            b=load_intake_bundle(_store(ns), _sid(ns)); form=create_formal_work_request_from_confirmed_specification(b[STORE_FILES['candidate']], b[STORE_FILES['confirmation']], repository_root_reference='.', repository_identity={'repository_id':'default'}); out=persist_formalized(_store(ns), b[STORE_FILES['intake']]['intake_id'], form);
        elif ns.cmd=='resume':
            bundle=load_session_store(_store(ns), _sid(ns)) if _sid(ns) else {}
            out=resume_multifile_state(bundle) if bundle.get('planning/multifile-change-plan-candidate.json') else (resume_practical_state({'package':bundle.get('work-entry/governed-change-package.json'),'approval':bundle.get('work-entry/approval.json'),'authorization':bundle.get('work-entry/authorization.json'),'admitted':bundle.get('work-entry/adapter-admission.json'),'evidence':bundle.get('execution/practical-execution-evidence.json'),'verification':bundle.get('verification/practical-verification.json')}) if bundle.get('work-entry/governed-change-package.json') else resume_natural_language_intake(_store(ns), session_id=_sid(ns)))
        elif ns.cmd in {'status','inspect'}:
            bundle=load_session_store(_store(ns), _sid(ns)) if _sid(ns) else {}
            out={**build_operator_status(_store(ns), session_id=_sid(ns)), **inspect_natural_language_intake(_store(ns), session_id=_sid(ns)), **inspect_practical_state(bundle), **inspect_multifile_state(bundle)}

        elif ns.cmd=='build-multifile-plan':
            b=load_session_store(_store(ns), _sid(ns)); spec=b.get('work-entry/specification-candidate.json') or {'confirmed_scope':['docs/status.txt'],'acceptance_criteria':['bounded_acceptance']}; wr=b.get('work-entry/request.json') or {'requested_scope':spec.get('confirmed_scope'),'repository_identity':{'repository_id':'default'}}; ra=b.get('work-entry/stages/repository-analysis.json') or {'observed_paths':spec.get('confirmed_scope')}; plan=build_multifile_change_plan_candidate(confirmed_specification=spec, work_request=wr, repository_analysis=ra, repository_identity=wr.get('repository_identity')); write_session_artifact(_store(ns), _sid(ns), 'planning/multifile-change-plan-candidate.json', plan); out=plan
        elif ns.cmd=='validate-multifile-plan':
            b=load_session_store(_store(ns), _sid(ns)); out=validate_multifile_change_plan_candidate(b['planning/multifile-change-plan-candidate.json'], confirmed_specification=b.get('work-entry/specification-candidate.json'), work_request=b.get('work-entry/request.json'), repository_analysis=b.get('work-entry/stages/repository-analysis.json'))
        elif ns.cmd=='multifile-plan':
            b=load_session_store(_store(ns), _sid(ns)); out=b.get('planning/multifile-change-plan-candidate.json', {'multifile_coding_workflow_status':'not_initialized'})
        elif ns.cmd in {'confirm-multifile-plan','reject-multifile-plan'}:
            b=load_session_store(_store(ns), _sid(ns)); raw=_load(ns.json_file); raw['decision']='rejected' if ns.cmd=='reject-multifile-plan' else raw.get('decision','confirmed'); out=confirm_multifile_change_plan(b['planning/multifile-change-plan-candidate.json'], raw); write_session_artifact(_store(ns), _sid(ns), 'planning/multifile-change-plan-confirmation.json', out)
        elif ns.cmd=='revise-multifile-plan':
            b=load_session_store(_store(ns), _sid(ns)); out=revise_multifile_change_plan(b['planning/multifile-change-plan-candidate.json'], _load(ns.json_file)); write_session_artifact(_store(ns), _sid(ns), 'planning/multifile-change-plan-candidate.json', out)
        elif ns.cmd=='formalize-multifile-plan':
            b=load_session_store(_store(ns), _sid(ns)); raw=_load(ns.json_file); out=formalize_confirmed_multifile_plan(plan=b['planning/multifile-change-plan-candidate.json'], confirmation=b['planning/multifile-change-plan-confirmation.json'], approved_proposal=raw.get('approved_proposal',{}), authorization=raw.get('authorization',{}), operation_definitions=raw.get('operation_definitions',[]), confirmed_specification=raw.get('confirmed_specification') or b.get('work-entry/specification-candidate.json',{}), work_request=raw.get('work_request') or b.get('work-entry/request.json',{}), repository_analysis=b.get('work-entry/stages/repository-analysis.json',{}));
            (write_session_artifact(_store(ns), _sid(ns), 'work-entry/governed-change-package.json', out['change_package']) if out.get('change_package') else None)
        elif ns.cmd=='test-set':
            b=load_session_store(_store(ns), _sid(ns)); pkg=b.get('work-entry/governed-change-package.json',{}); plan=b.get('planning/multifile-change-plan-candidate.json',{}); out=run_bounded_test_set(pkg, plan.get('test_strategy',{}).get('required_test_targets',[]), workspace_root=pkg.get('workspace_root','.'), stop_policy=plan.get('test_strategy',{}).get('stop_policy','first_failure')) if ns.execute else {'test_execution_order':plan.get('test_strategy',{}).get('execution_order',[]),'will_execute_tests':False};
            (write_session_artifact(_store(ns), _sid(ns), 'testing/bounded-test-set-result.json', out) if ns.execute else None)
        elif ns.cmd=='test-failure-evidence':
            b=load_session_store(_store(ns), _sid(ns)); pkg=b.get('work-entry/governed-change-package.json',{}); out=build_test_failure_evidence(execution=b.get('execution/practical-execution-evidence.json',{}), verification=b.get('verification/practical-verification.json',{}), test_set=b.get('testing/bounded-test-set-result.json',{}), changed_paths=pkg.get('expected_changed_paths',[]), confirmed_scope=pkg.get('confirmed_scope',[])); write_session_artifact(_store(ns), _sid(ns), 'testing/test-failure-evidence.json', out)
        elif ns.cmd=='repair-candidate':
            b=load_session_store(_store(ns), _sid(ns)); pkg=b.get('work-entry/governed-change-package.json',{}); out=build_repair_proposal_candidate(parent_work_request=b.get('work-entry/request.json',{}), parent_change_package=pkg, parent_execution=b.get('execution/practical-execution-evidence.json',{}), test_failure_evidence=b.get('testing/test-failure-evidence.json',{}), confirmed_scope=pkg.get('confirmed_scope',[])); write_session_artifact(_store(ns), _sid(ns), 'feedback/repair-proposal-candidate.json', out)
        elif ns.cmd=='review-repair-candidate':
            b=load_session_store(_store(ns), _sid(ns)); out=review_repair_candidate(b['feedback/repair-proposal-candidate.json'], _load(ns.json_file)); write_session_artifact(_store(ns), _sid(ns), 'feedback/repair-candidate-review.json', out)
        elif ns.cmd=='iteration-status':
            b=load_session_store(_store(ns), _sid(ns)); out=b.get('iterations/iteration-index.json') or build_iteration_index([])
        elif ns.cmd=='prepare': out=prepare_operator_flow(_store(ns), session_id=_sid(ns), repository=ns.repository)
        elif ns.cmd=='review': out={'schema':'zero.engineering.operator_review_summary.v1','status':build_operator_status(_store(ns), session_id=_sid(ns)),'ready_for_approval':build_operator_status(_store(ns), session_id=_sid(ns)).get('approval_status')=='pending','approved':False,'read_only':True}
        elif ns.cmd=='approval-summary':
            st=build_operator_status(_store(ns), session_id=_sid(ns)); out={'schema':'zero.engineering.approval_summary.v1','task_statement':st.get('work_request_statement'),'repository':st.get('repository_identity'),'bounded_scope':(st.get('operator_flow') or {}).get('work_request_reference'),'excluded_scope':[],'proposed_ordered_operations':'see activation ordered_operations','affected_paths':[],'risk_summary':'human must review proposal','validation_plan':'existing proposal validation plan','rollback_recovery':'use VCS or execution recovery evidence','proposal_review_findings':'ready_for_approval is not approval','approval_conditions':[],'human_decision_options':['approve','reject','return_for_changes'],'not_approval_artifact':True,'governance_warning':'這不是 Approval artifact；沒有批准權限；正式批准必須透過既有 Approval contract 提供。'}
        elif ns.cmd=='attach-approval':
            res=resolve_active_engineering_work(_store(ns), session_id=_sid(ns)); b=res['bundle']; act=b.get('work-entry/execution-activation.json') or create_demo_activation(_store(ns), session_id=res['session_id']) ; appr=_load(ns.approval_json); act2=attach_human_approval(act,appr); persist_activation_artifacts(_store(ns),res['session_id'],activation=act2,approval=appr); out={'approval_status':'validated','approval_actor':appr.get('human_actor'),'approval_scope':appr.get('approved_scope'),'conditions':appr.get('conditions',[]),'next_step':'authorization-summary'}
        elif ns.cmd=='authorization-summary':
            res=resolve_active_engineering_work(_store(ns), session_id=_sid(ns)); b=res['bundle']; act=b.get('work-entry/execution-activation.json') or create_demo_activation(_store(ns), session_id=res['session_id']); appr=b.get('work-entry/approval.json'); hand=create_authorization_handoff(act,appr) if appr else None; out={'schema':'zero.engineering.authorization_summary.v1','approved_proposal':act.get('proposal_reference'),'approved_scope':(appr or {}).get('approved_scope'),'exact_ordered_operation_package':act.get('ordered_operations'),'workspace_identity':act.get('workspace_reference'),'adapter_requirements':'zero.text_file_create v1','execution_risks':'bounded text create only','expected_changed_paths':[o.get('path') for o in act.get('ordered_operations',[])],'expected_unchanged_paths':[],'authorization_conditions':(appr or {}).get('conditions',[]),'authorization_consumption_semantics':'consumed after successful execution; cannot replay or expand operation','replay_warning':'授權只適用這一次 sealed execution package；不能重放。','human_decision_options':['authorize','reject','return_for_changes'],'not_execution_token':True};
            if hand: persist_activation_artifacts(_store(ns),res['session_id'],authorization_handoff=hand)
        elif ns.cmd=='attach-authorization':
            res=resolve_active_engineering_work(_store(ns), session_id=_sid(ns)); b=res['bundle']; appr=_load(ns.approval_json) if ns.approval_json else b['work-entry/approval.json']; auth=_load(ns.authorization_json); act2=attach_human_authorization(b['work-entry/execution-activation.json'],auth,appr); persist_activation_artifacts(_store(ns),res['session_id'],activation=act2,authorization=auth); out={'authorization_status':'valid','authority':'exact_package','execution_started':False,'next_step':'prepare-execution'}
        elif ns.cmd=='prepare-execution':
            res=resolve_active_engineering_work(_store(ns), session_id=_sid(ns)); b=res['bundle']; auth=_load(ns.authorization_json) if ns.authorization_json else b['work-entry/authorization.json']; prep,act=prepare_execution(b['work-entry/execution-activation.json'],auth,workspace_root=ns.workspace_root); persist_activation_artifacts(_store(ns),res['session_id'],activation=act,execution_preparation=prep); out={'execution_preparation':prep,'activation':act}
        elif ns.cmd=='admit-adapter':
            res=resolve_active_engineering_work(_store(ns), session_id=_sid(ns)); b=res['bundle']; prep=_load(ns.preparation_json) if ns.preparation_json else b['work-entry/execution-preparation.json']; adm,act=admit_adapter(b['work-entry/execution-activation.json'],prep); persist_activation_artifacts(_store(ns),res['session_id'],activation=act,adapter_admission=adm); out={'adapter_admission':adm,'activation':act}
        elif ns.cmd=='preview':
            bundle=load_session_store(_store(ns), _sid(ns)) if _sid(ns) else {}
            out=preview_practical_execution(bundle['work-entry/governed-change-package.json']) if bundle.get('work-entry/governed-change-package.json') else preview_execution(_store(ns), session_id=_sid(ns))
        elif ns.cmd=='execute':
            if not ns.confirm_execution: out={'valid':False,'error':'execution_confirmation_required','mutation_occurred':False}; _emit(out, ns.format, ns.verbose); return 8
            bundle=load_session_store(_store(ns), _sid(ns)) if _sid(ns) else {}
            if bundle.get('work-entry/governed-change-package.json'):
                auth=bundle.get('work-entry/authorization.json',{})
                out=execute_practical_change_package(bundle['work-entry/governed-change-package.json'], approval=bundle.get('work-entry/approval.json',{}), authorization=auth, admitted=bool(bundle.get('work-entry/adapter-admission.json')), confirm_execution=True, workspace_root=ns.workspace_root)
                write_session_artifact(_store(ns), _sid(ns), 'execution/practical-execution-evidence.json', out)
                if out.get('authorization_consumed'):
                    auth={**auth,'consumption_state':'consumed'}; write_session_artifact(_store(ns), _sid(ns), 'work-entry/authorization.json', auth)
            else:
                            res=resolve_active_engineering_work(_store(ns), session_id=_sid(ns)); b=res['bundle']; auth=_load(ns.authorization_json) if ns.authorization_json else b['work-entry/authorization.json']; prep=_load(ns.preparation_json) if ns.preparation_json else b['work-entry/execution-preparation.json']; adm=_load(ns.admission_json) if ns.admission_json else b['work-entry/adapter-admission.json']; er,auth2,act=activate_governed_execution(b['work-entry/execution-activation.json'],auth,prep,adm,workspace_root=ns.workspace_root); persist_activation_artifacts(_store(ns),res['session_id'],activation=act,authorization=auth2,execution_result=er); out={'execution_result':er,'authorization':auth2,'activation':act}
        elif ns.cmd=='build-change-package':
            plan=_load(ns.operations_json); sid=_sid(ns) or plan.get('session_id','practical-v40'); pkg=build_governed_change_package(confirmed_specification=plan.get('confirmed_specification'), work_request=plan.get('work_request'), read_only_analysis=plan.get('read_only_analysis'), proposal=plan.get('proposal'), operation_plan=plan.get('ordered_operations') or plan.get('operations'), repository_identity=plan.get('repository_identity'), workspace_root=plan.get('workspace_root','.'), expected_unchanged_paths=plan.get('expected_unchanged_paths',[]), risk_level=plan.get('risk_level','medium')); write_session_artifact(_store(ns), sid, 'work-entry/governed-change-package.json', pkg); write_session_artifact(_store(ns), sid, 'execution/bounded-test-policy.json', bounded_test_policy()); out={'operation_count':len(pkg['ordered_operations']),'created_files':[o.get('target_path') for o in pkg['ordered_operations'] if o.get('operation_type')=='create_text_file'],'modified_files':[o.get('target_path') for o in pkg['ordered_operations'] if o.get('operation_type') in {'replace_text_exact','append_text','remove_text_exact'}],'renamed_files':[o.get('target_path') for o in pkg['ordered_operations'] if o.get('operation_type')=='rename_file'],'test_targets':[o.get('test_targets') or [o.get('target_path')] for o in pkg['ordered_operations'] if o.get('operation_type')=='run_bounded_test'],'risk':pkg['risk_level'],'approval_required':True,'authorization_required':True,'change_package':pkg}
        elif ns.cmd=='validate-change-package':
            bundle=load_session_store(_store(ns), _sid(ns)); out=validate_governed_change_package(bundle['work-entry/governed-change-package.json'])
        elif ns.cmd=='change-package':
            bundle=load_session_store(_store(ns), _sid(ns)); pkg=bundle['work-entry/governed-change-package.json']; out={'change_package_id':pkg['change_package_id'],'change_package_fingerprint':pkg['change_package_fingerprint'],'ordered_operations':[{k:o.get(k) for k in ('operation_id','operation_type','target_path','source_path')} for o in pkg['ordered_operations']],'expected_changed_paths':pkg['expected_changed_paths'],'execution_status':'尚未執行','repository_modified':False}
        elif ns.cmd=='execution-evidence':
            bundle=load_session_store(_store(ns), _sid(ns)); out=bundle.get('execution/practical-execution-evidence.json', {'evidence_status':'not_started'})
        elif ns.cmd=='run-tests':
            bundle=load_session_store(_store(ns), _sid(ns)); pkg=bundle['work-entry/governed-change-package.json']; out={'test_results':[run_bounded_test_operation(o, Path(pkg.get('workspace_root','.') ), bounded_test_policy()) for o in pkg['ordered_operations'] if o.get('operation_type')=='run_bounded_test']}
        elif ns.cmd=='verify':
            bundle=load_session_store(_store(ns), _sid(ns)) if _sid(ns) else {}
            if bundle.get('work-entry/governed-change-package.json'):
                ver=verify_practical_repository_execution(bundle['work-entry/governed-change-package.json'], bundle.get('execution/practical-execution-evidence.json',{})); write_session_artifact(_store(ns), _sid(ns), 'verification/practical-verification.json', ver); out={'verification':ver}
            else:
                res=resolve_active_engineering_work(_store(ns), session_id=_sid(ns)); b=res['bundle']; er=_load(ns.execution_json) if ns.execution_json else b['work-entry/execution-result.json']; ver,act=verify_execution(b['work-entry/execution-activation.json'],er); persist_activation_artifacts(_store(ns),res['session_id'],activation=act,verification=ver); out={'verification':ver,'activation':act}
        elif ns.cmd=='evaluate-progress':
            res=resolve_active_engineering_work(_store(ns), session_id=_sid(ns)); b=res['bundle']; ver=_load(ns.verification_json) if ns.verification_json else b['work-entry/verification.json']; pr,act=evaluate_progress(b['work-entry/execution-activation.json'],ver); persist_activation_artifacts(_store(ns),res['session_id'],activation=act,progress=pr); out={'progress':pr,'activation':act}
        elif ns.cmd=='result':
            bundle=load_session_store(_store(ns), _sid(ns)) if _sid(ns) else {}
            out=practical_result(bundle.get('work-entry/governed-change-package.json'),bundle.get('execution/practical-execution-evidence.json'),bundle.get('verification/practical-verification.json')) if bundle.get('work-entry/governed-change-package.json') else {'schema':'zero.engineering.operator_result.v1','status':build_operator_status(_store(ns), session_id=_sid(ns)),'executed':False,'verified':False,'completion_candidate':False,'human_completion_accepted':False,'next_governed_action':'completion-review-summary'}
        elif ns.cmd=='resume':
            st=build_operator_status(_store(ns), session_id=_sid(ns)); out={'schema':'zero.engineering.operator_resume_guidance.v1','canonical_status':st,'guidance':st.get('recommended_command'),'will_auto_execute':False}
        elif ns.cmd=='completion-review-summary': out={'schema':'zero.engineering.completion_review_summary.v1','human_decision_options':['accept_completion','continue_iteration','request_changes','stop'],'not_completion_decision':True,'manual_artifact_required':True,'status':build_operator_status(_store(ns), session_id=_sid(ns))}
        elif ns.cmd=='verify-flow': out={'valid':True,'status':build_operator_status(_store(ns), session_id=_sid(ns))}
        elif ns.cmd=='submit':
            req=create_engineering_work_request(request_statement=ns.statement,repository_identity={'repository_id':ns.repo_id},repository_root_reference=ns.repo_root,requested_scope=['docs/status.txt']); i=admit_engineering_work(req); c=create_work_coordination(req,i); pl=create_read_only_pipeline(req,i,c); out={'work_request':req,'work_intake':i,'coordination':c,'read_only_pipeline':pl}
        else: out={'valid':False,'error':'unsupported_existing_contract'}
        _emit(out, ns.format, ns.verbose); return 0
    except (WorkEntryError, ReadOnlyPipelineError, ActivationError, NaturalLanguageIntakeError) as e:
        _emit({'valid':False,'error':e.code,'current_phase':'blocked','mutation_occurred':False,'safe_next_action':'resume','recovery_guidance':'請檢查治理產物後重試。'}, ns.format, ns.verbose); return 5
    except Exception as e:
        _emit({'valid':False,'error':str(e),'mutation_occurred':False}, ns.format, ns.verbose); return 6
if __name__=='__main__': raise SystemExit(main())
