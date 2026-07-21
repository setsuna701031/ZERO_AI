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
from core.engineering.engineering_governed_bug_reproduction import STORE_FILES as REPRO_STORE_FILES, admit_bounded_reproduction, build_reproduction_request_candidate, capture_workspace_snapshot, confirm_reproduction_request, inspect_reproduction_state, resume_reproduction_state, run_reproduction, validate_reproduction_request
from core.engineering.engineering_governed_repair_planning import STORE_FILES as REPAIR_STORE_FILES, build_patch_candidate, build_repair_impact_analysis, build_repair_planning_intake, build_repair_strategy_candidate, build_root_cause_hypothesis, inspect_repair_planning_state, resume_repair_planning_state, review_patch_candidate, revise_patch_candidate, validate_patch_candidate
from core.engineering.engineering_governed_patch_authoring import STORE_FILES as AUTHOR_STORE_FILES, author_file_edits, build_candidate_diff, build_patch_authoring_intake, inspect_patch_authoring_state, resume_patch_authoring_state, review_authored_patch, snapshot_patch_sources, validate_authored_patch
from core.engineering.engineering_governed_patch_authorization import STORE_FILES as AUTHZ_STORE_FILES, build_authorization_request, build_authorized_change_package, build_change_package_candidate, build_change_package_preparation, decide_patch_authorization, inspect_patch_authorization_state, resume_patch_authorization_state, review_change_package, revise_change_package_candidate, validate_change_package_candidate, verify_patch_readiness
from core.engineering.engineering_governed_explicit_patch_apply import STORE_FILES as APPLY_STORE_FILES, admit_patch_apply, apply_authorized_patch, build_completion_review_candidate, build_explicit_apply_request, inspect_explicit_apply_state, reserve_authorization, resume_explicit_apply_state, review_completion, verify_applied_patch
from core.engineering.engineering_practical_task_runner import _ref
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
    for c in ('status','inspect','review','approval-summary','authorization-summary','preview','result','resume','completion-review-summary','verify-flow','intake-status','specification','clarification','formalize','start-confirmed','validate-change-package','change-package','execution-evidence','run-tests','build-multifile-plan','validate-multifile-plan','multifile-plan','validate-reproduction-request','reproduction-request','reproduction-result','test-failure-evidence','repair-candidate','iteration-status','build-repair-planning-intake','root-cause-hypothesis','impact-analysis','repair-strategy','build-patch-candidate','validate-patch-candidate','patch-candidate','build-patch-authoring-intake','authored-patch','prepare-change-package','build-patch-authorization-request','authorized-change-package','patch-apply-result','patch-verification-result','completion-review-candidate'):
        sub.add_parser(c)
    brr=sub.add_parser('build-reproduction-request'); brr.add_argument('request_json'); brr.add_argument('--workspace-root',default='.')
    for name in ('confirm-reproduction','reject-reproduction'):
        sp=sub.add_parser(name); sp.add_argument('confirmation_json')
    rr=sub.add_parser('run-reproduction'); rr.add_argument('--workspace-root',default='.')
    for name in ('review-patch-candidate','reject-patch-candidate','revise-patch-candidate'):
        sp=sub.add_parser(name); sp.add_argument('json_file')
    snap=sub.add_parser('snapshot-patch-sources'); snap.add_argument('--workspace-root',default='.')
    afe=sub.add_parser('author-file-edits'); afe.add_argument('json_file')
    vap=sub.add_parser('validate-authored-patch'); vap.add_argument('--workspace-root',default='.')
    for name in ('review-authored-patch','reject-authored-patch','revise-authored-patch'):
        sp=sub.add_parser(name); sp.add_argument('json_file')
    for name in ('review-change-package','reject-change-package','revise-change-package','authorize-patch','reject-patch-authorization'):
        sp=sub.add_parser(name); sp.add_argument('json_file')
    vpr=sub.add_parser('verify-patch-readiness'); vpr.add_argument('--workspace-root',default='.')
    for name in ('build-explicit-apply-request','confirm-explicit-apply','reject-explicit-apply','review-completion'):
        sp=sub.add_parser(name); sp.add_argument('json_file')
    aap=sub.add_parser('apply-authorized-patch'); aap.add_argument('--workspace-root',default='.')
    apa=sub.add_parser('admit-patch-apply'); apa.add_argument('--workspace-root',default='.')
    vap2=sub.add_parser('verify-applied-patch'); vap2.add_argument('--workspace-root',default='.')
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
            b=load_intake_bundle(_store(ns), _sid(ns)); intake=b[STORE_FILES['intake']]; sid=intake['intake_id']; evidence=b[STORE_FILES['evidence']]; repo_identity={'repository_id':intake.get('repository_reference',{}).get('repository_id','default'),**evidence.get('repository_identity',{})}; finalized=persist_finalized_intake(_store(ns),sid,intake,b[STORE_FILES['candidate']],b[STORE_FILES['confirmation']]); form=create_formal_work_request_from_confirmed_specification(b[STORE_FILES['candidate']], b[STORE_FILES['confirmation']], repository_root_reference='.', repository_identity=repo_identity, finalized_intake=finalized); out=persist_formalized(_store(ns),sid,form);
        elif ns.cmd=='resume':
            bundle=load_session_store(_store(ns), _sid(ns)) if _sid(ns) else {}
            out=resume_explicit_apply_state(bundle) if any(bundle.get(x) for x in APPLY_STORE_FILES.values()) else (resume_patch_authorization_state(bundle) if bundle.get(AUTHOR_STORE_FILES['review']) or any(bundle.get(x) for x in AUTHZ_STORE_FILES.values()) else (resume_patch_authoring_state(bundle) if bundle.get(REPAIR_STORE_FILES['review']) or any(bundle.get(x) for x in AUTHOR_STORE_FILES.values()) else (resume_repair_planning_state(bundle) if bundle.get(REPRO_STORE_FILES['repair_review']) or any(bundle.get(x) for x in REPAIR_STORE_FILES.values()) else (resume_reproduction_state(bundle) if any(bundle.get(x) for x in REPRO_STORE_FILES.values()) else (resume_multifile_state(bundle) if bundle.get('planning/multifile-change-plan-candidate.json') else (resume_practical_state({'package':bundle.get('work-entry/governed-change-package.json'),'approval':bundle.get('work-entry/approval.json'),'authorization':bundle.get('work-entry/authorization.json'),'admitted':bundle.get('work-entry/adapter-admission.json'),'evidence':bundle.get('execution/practical-execution-evidence.json'),'verification':bundle.get('verification/practical-verification.json')}) if bundle.get('work-entry/governed-change-package.json') else resume_natural_language_intake(_store(ns), session_id=_sid(ns))))))))
        elif ns.cmd in {'status','inspect'}:
            bundle=load_session_store(_store(ns), _sid(ns)) if _sid(ns) else {}
            out={**build_operator_status(_store(ns), session_id=_sid(ns)), **inspect_natural_language_intake(_store(ns), session_id=_sid(ns)), **inspect_practical_state(bundle), **inspect_multifile_state(bundle), **inspect_reproduction_state(bundle), **inspect_repair_planning_state(bundle), **inspect_patch_authoring_state(bundle), **inspect_patch_authorization_state(bundle), **inspect_explicit_apply_state(bundle)}

        elif ns.cmd=='build-multifile-plan':
            b=load_session_store(_store(ns), _sid(ns)); legacy_spec=b.get(STORE_FILES['candidate']); spec=b.get(STORE_FILES['confirmation']) or (legacy_spec if (legacy_spec or {}).get('schema')=='zero.engineering.confirmed_specification.v1' else None); wr=b.get('work-entry/request.json'); ra=b.get('work-entry/stages/repository-analysis.json') or b.get(STORE_FILES['evidence'])
            if not spec: raise ActivationError('requires_specification_confirmation')
            if not wr: raise ActivationError('missing_work_request')
            if not ra: raise ActivationError('missing_repository_analysis')
            plan=build_multifile_change_plan_candidate(confirmed_specification=spec, work_request=wr, repository_analysis=ra, repository_identity=wr.get('repository_identity'), session_id=_sid(ns)); write_session_artifact(_store(ns), _sid(ns), 'planning/multifile-change-plan-candidate.json', plan); out=plan
        elif ns.cmd=='validate-multifile-plan':
            b=load_session_store(_store(ns), _sid(ns)); legacy_spec=b.get(STORE_FILES['candidate']); spec=b.get(STORE_FILES['confirmation']) or (legacy_spec if (legacy_spec or {}).get('schema')=='zero.engineering.confirmed_specification.v1' else None); out=validate_multifile_change_plan_candidate(b['planning/multifile-change-plan-candidate.json'], confirmed_specification=spec, work_request=b.get('work-entry/request.json'), repository_analysis=b.get('work-entry/stages/repository-analysis.json') or b.get(STORE_FILES['evidence']), session_id=_sid(ns), finalized_intake=b.get(STORE_FILES['finalized_intake']))
        elif ns.cmd=='multifile-plan':
            b=load_session_store(_store(ns), _sid(ns)); out=b.get('planning/multifile-change-plan-candidate.json', {'multifile_coding_workflow_status':'not_initialized'})
        elif ns.cmd=='build-reproduction-request':
            b=load_session_store(_store(ns),_sid(ns)); raw=_load(ns.request_json); plan=b.get('planning/multifile-change-plan-candidate.json',{}); targets=raw.get('target_test_nodes') or raw.get('target_test_files') or plan.get('test_strategy',{}).get('required_test_targets',[]); snapshot=capture_workspace_snapshot(ns.workspace_root,targets); out=build_reproduction_request_candidate(work_request=b.get('work-entry/request.json',{}),confirmed_specification=b.get(STORE_FILES['confirmation'],{}),human_plan_confirmation=b.get('planning/multifile-change-plan-confirmation.json',{}),repository_analysis=b.get('work-entry/stages/repository-analysis.json') or b.get(STORE_FILES['evidence'],{}),repository_identity=raw.get('repository_identity') or plan.get('repository_identity',{}),confirmed_scope=raw.get('confirmed_scope') or [c.get('path') for c in plan.get('ordered_file_changes',[])],target_test_files=raw.get('target_test_files') or [str(t).split('::')[0] for t in targets],target_test_nodes=raw.get('target_test_nodes',[]),expected_behavior=raw.get('expected_behavior','confirmed expected behavior'),observed_behavior=raw.get('observed_behavior','reported defect behavior'),reproduction_steps=raw.get('reproduction_steps',['run confirmed bounded pytest target']),workspace_snapshot=snapshot,session_id=_sid(ns),timeout_seconds=int(raw.get('timeout_seconds',120)),stop_policy=raw.get('stop_policy','first_failure')); write_session_artifact(_store(ns),_sid(ns),REPRO_STORE_FILES['request'],out); write_session_artifact(_store(ns),_sid(ns),'reproduction/workspace-snapshot.json',snapshot)
        elif ns.cmd=='validate-reproduction-request':
            b=load_session_store(_store(ns),_sid(ns)); out={'valid':not validate_reproduction_request(b.get(REPRO_STORE_FILES['request'],{}),workspace_snapshot=b.get('reproduction/workspace-snapshot.json'),session_id=_sid(ns)),'errors':validate_reproduction_request(b.get(REPRO_STORE_FILES['request'],{}),workspace_snapshot=b.get('reproduction/workspace-snapshot.json'),session_id=_sid(ns))}
        elif ns.cmd=='reproduction-request':
            out=load_session_store(_store(ns),_sid(ns)).get(REPRO_STORE_FILES['request'],{'status':'not_started'})
        elif ns.cmd in {'confirm-reproduction','reject-reproduction'}:
            b=load_session_store(_store(ns),_sid(ns)); raw=_load(ns.confirmation_json); raw['decision']='rejected' if ns.cmd=='reject-reproduction' else raw.get('decision','confirmed'); out=confirm_reproduction_request(b[REPRO_STORE_FILES['request']],raw); write_session_artifact(_store(ns),_sid(ns),REPRO_STORE_FILES['confirmation'],out)
        elif ns.cmd=='run-reproduction':
            b=load_session_store(_store(ns),_sid(ns)); request=b[REPRO_STORE_FILES['request']]; confirmation=b[REPRO_STORE_FILES['confirmation']]; snapshot=b['reproduction/workspace-snapshot.json']; admission=admit_bounded_reproduction(request,confirmation,workspace_snapshot=snapshot,repository_identity=request['repository_identity'],session_id=_sid(ns)); write_session_artifact(_store(ns),_sid(ns),REPRO_STORE_FILES['admission'],admission)
            if admission.get('admission_status')!='admitted': out={'reproduction_status':'blocked','admission':admission}
            else:
                result,test_set,consumed=run_reproduction(request,confirmation,admission,workspace_root=ns.workspace_root,workspace_snapshot=snapshot); write_session_artifact(_store(ns),_sid(ns),REPRO_STORE_FILES['admission'],consumed); write_session_artifact(_store(ns),_sid(ns),REPRO_STORE_FILES['test_set'],test_set); write_session_artifact(_store(ns),_sid(ns),REPRO_STORE_FILES['result'],result); out=result
        elif ns.cmd=='reproduction-result':
            out=load_session_store(_store(ns),_sid(ns)).get(REPRO_STORE_FILES['result'],{'reproduction_status':'not_started'})
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
            b=load_session_store(_store(ns), _sid(ns)); pkg=b.get('work-entry/governed-change-package.json',{}); request=b.get(REPRO_STORE_FILES['request'],{}); out=build_test_failure_evidence(execution=b.get('execution/practical-execution-evidence.json',{}), verification=b.get('verification/practical-verification.json',{}), test_set=b.get(REPRO_STORE_FILES['test_set']) or b.get('testing/bounded-test-set-result.json',{}), changed_paths=pkg.get('expected_changed_paths',[]), confirmed_scope=request.get('confirmed_scope') or pkg.get('confirmed_scope',[])); write_session_artifact(_store(ns), _sid(ns), REPRO_STORE_FILES['failure_evidence'] if request else 'testing/test-failure-evidence.json', out)
        elif ns.cmd=='repair-candidate':
            b=load_session_store(_store(ns), _sid(ns)); pkg=b.get('work-entry/governed-change-package.json',{}); request=b.get(REPRO_STORE_FILES['request'],{}); evidence=b.get(REPRO_STORE_FILES['failure_evidence']) or b.get('testing/test-failure-evidence.json',{}); out=build_repair_proposal_candidate(parent_work_request=b.get('work-entry/request.json',{}), parent_change_package=pkg, parent_execution=b.get(REPRO_STORE_FILES['result']) or b.get('execution/practical-execution-evidence.json',{}), test_failure_evidence=evidence, confirmed_scope=request.get('confirmed_scope') or pkg.get('confirmed_scope',[])); write_session_artifact(_store(ns), _sid(ns), REPRO_STORE_FILES['repair_candidate'] if request else 'feedback/repair-proposal-candidate.json', out)
        elif ns.cmd=='review-repair-candidate':
            b=load_session_store(_store(ns), _sid(ns)); candidate=b.get(REPRO_STORE_FILES['repair_candidate']) or b['feedback/repair-proposal-candidate.json']; out=review_repair_candidate(candidate, _load(ns.json_file)); write_session_artifact(_store(ns), _sid(ns), REPRO_STORE_FILES['repair_review'] if b.get(REPRO_STORE_FILES['repair_candidate']) else 'feedback/repair-candidate-review.json', out)
        elif ns.cmd=='build-repair-planning-intake':
            b=load_session_store(_store(ns),_sid(ns)); request=b.get(REPRO_STORE_FILES['request'],{}); plan=b.get('planning/multifile-change-plan-candidate.json',{}); out=build_repair_planning_intake(work_request=b.get('work-entry/request.json',{}),confirmed_specification=b.get(STORE_FILES['confirmation'],{}),human_plan_confirmation=b.get('planning/multifile-change-plan-confirmation.json',{}),reproduction_result=b.get(REPRO_STORE_FILES['result'],{}),test_failure_evidence=b.get(REPRO_STORE_FILES['failure_evidence'],{}),repair_proposal_candidate=b.get(REPRO_STORE_FILES['repair_candidate'],{}),human_repair_review=b.get(REPRO_STORE_FILES['repair_review'],{}),repository_identity=request.get('repository_identity') or plan.get('repository_identity',{}),confirmed_scope=request.get('confirmed_scope') or [x.get('path') for x in plan.get('ordered_file_changes',[])],iteration_reference=b.get('iterations/iteration-index.json',{}),session_id=_sid(ns)); write_session_artifact(_store(ns),_sid(ns),REPAIR_STORE_FILES['planning_intake'],out)
        elif ns.cmd=='root-cause-hypothesis':
            b=load_session_store(_store(ns),_sid(ns)); out=build_root_cause_hypothesis(b[REPAIR_STORE_FILES['planning_intake']],b[REPRO_STORE_FILES['failure_evidence']],b[REPRO_STORE_FILES['repair_candidate']]); write_session_artifact(_store(ns),_sid(ns),REPAIR_STORE_FILES['hypothesis'],out)
        elif ns.cmd=='impact-analysis':
            b=load_session_store(_store(ns),_sid(ns)); out=build_repair_impact_analysis(b[REPAIR_STORE_FILES['planning_intake']],b[REPAIR_STORE_FILES['hypothesis']],b[REPRO_STORE_FILES['failure_evidence']],b[REPRO_STORE_FILES['repair_candidate']],b.get('work-entry/stages/repository-analysis.json') or b.get(STORE_FILES['evidence'],{})); write_session_artifact(_store(ns),_sid(ns),REPAIR_STORE_FILES['impact'],out)
        elif ns.cmd=='repair-strategy':
            b=load_session_store(_store(ns),_sid(ns)); out=build_repair_strategy_candidate(b[REPAIR_STORE_FILES['planning_intake']],b[REPAIR_STORE_FILES['hypothesis']],b[REPAIR_STORE_FILES['impact']]); write_session_artifact(_store(ns),_sid(ns),REPAIR_STORE_FILES['strategy'],out)
        elif ns.cmd=='build-patch-candidate':
            b=load_session_store(_store(ns),_sid(ns)); spec=b.get(STORE_FILES['confirmation'],{}); out=build_patch_candidate(b[REPAIR_STORE_FILES['planning_intake']],b[REPAIR_STORE_FILES['strategy']],b[REPAIR_STORE_FILES['impact']],acceptance_criteria=spec.get('confirmed_acceptance_criteria') or ['bounded reproduced behavior is addressed']); write_session_artifact(_store(ns),_sid(ns),REPAIR_STORE_FILES['patch'],out)
        elif ns.cmd=='validate-patch-candidate':
            b=load_session_store(_store(ns),_sid(ns)); planning=b.get(REPAIR_STORE_FILES['planning_intake'],{}); out=validate_patch_candidate(b.get(REPAIR_STORE_FILES['patch'],{}),planning=planning,strategy=b.get(REPAIR_STORE_FILES['strategy']),impact=b.get(REPAIR_STORE_FILES['impact']),failure_evidence=b.get(REPRO_STORE_FILES['failure_evidence']),repair_candidate=b.get(REPRO_STORE_FILES['repair_candidate']),human_repair_review=b.get(REPRO_STORE_FILES['repair_review']),repository_analysis=b.get('work-entry/stages/repository-analysis.json') or b.get(STORE_FILES['evidence'],{}),repository_identity=planning.get('repository_identity'),session_id=_sid(ns),iteration_reference=planning.get('iteration_reference')); write_session_artifact(_store(ns),_sid(ns),REPAIR_STORE_FILES['validation'],out)
        elif ns.cmd=='patch-candidate':
            out=load_session_store(_store(ns),_sid(ns)).get(REPAIR_STORE_FILES['patch'],{'patch_candidate_status':'not_started'})
        elif ns.cmd in {'review-patch-candidate','reject-patch-candidate'}:
            b=load_session_store(_store(ns),_sid(ns)); raw=_load(ns.json_file); raw['decision']='rejected' if ns.cmd=='reject-patch-candidate' else raw.get('decision','confirmed'); out=review_patch_candidate(b[REPAIR_STORE_FILES['patch']],b[REPAIR_STORE_FILES['validation']],raw); write_session_artifact(_store(ns),_sid(ns),REPAIR_STORE_FILES['review'],out)
        elif ns.cmd=='revise-patch-candidate':
            b=load_session_store(_store(ns),_sid(ns)); out=revise_patch_candidate(b[REPAIR_STORE_FILES['patch']],_load(ns.json_file)); write_session_artifact(_store(ns),_sid(ns),REPAIR_STORE_FILES['patch'],out)
        elif ns.cmd=='build-patch-authoring-intake':
            b=load_session_store(_store(ns),_sid(ns)); planning=b[REPAIR_STORE_FILES['planning_intake']]; out=build_patch_authoring_intake(patch_candidate=b[REPAIR_STORE_FILES['patch']],patch_validation=b[REPAIR_STORE_FILES['validation']],human_patch_review=b[REPAIR_STORE_FILES['review']],repair_strategy=b[REPAIR_STORE_FILES['strategy']],impact_analysis=b[REPAIR_STORE_FILES['impact']],repository_identity=planning.get('repository_identity',{}),confirmed_scope=planning.get('confirmed_scope',[]),iteration_reference=planning.get('iteration_reference',{}),session_id=_sid(ns)); write_session_artifact(_store(ns),_sid(ns),AUTHOR_STORE_FILES['intake'],out)
        elif ns.cmd=='snapshot-patch-sources':
            b=load_session_store(_store(ns),_sid(ns)); out=snapshot_patch_sources(b[AUTHOR_STORE_FILES['intake']],b[REPAIR_STORE_FILES['patch']],workspace_root=ns.workspace_root); write_session_artifact(_store(ns),_sid(ns),AUTHOR_STORE_FILES['snapshots'],out)
        elif ns.cmd=='author-file-edits':
            b=load_session_store(_store(ns),_sid(ns)); raw=_load(ns.json_file); definitions=raw.get('definitions',[]) if isinstance(raw,dict) else raw; files,tests=author_file_edits(b[AUTHOR_STORE_FILES['intake']],b[REPAIR_STORE_FILES['patch']],b[AUTHOR_STORE_FILES['snapshots']],definitions); out=build_candidate_diff(b[AUTHOR_STORE_FILES['intake']],b[AUTHOR_STORE_FILES['snapshots']],files,tests); write_session_artifact(_store(ns),_sid(ns),AUTHOR_STORE_FILES['file_edits'],files); write_session_artifact(_store(ns),_sid(ns),AUTHOR_STORE_FILES['test_edits'],tests); write_session_artifact(_store(ns),_sid(ns),AUTHOR_STORE_FILES['diff'],out)
        elif ns.cmd=='validate-authored-patch':
            b=load_session_store(_store(ns),_sid(ns)); intake=b[AUTHOR_STORE_FILES['intake']]; out=validate_authored_patch(b[AUTHOR_STORE_FILES['diff']],intake=intake,patch_candidate=b[REPAIR_STORE_FILES['patch']],human_patch_review=b[REPAIR_STORE_FILES['review']],source_set=b[AUTHOR_STORE_FILES['snapshots']],file_edits=b[AUTHOR_STORE_FILES['file_edits']],test_edits=b[AUTHOR_STORE_FILES['test_edits']],workspace_root=ns.workspace_root,repository_identity=intake.get('repository_identity'),session_id=_sid(ns),iteration_reference=intake.get('iteration_reference')); write_session_artifact(_store(ns),_sid(ns),AUTHOR_STORE_FILES['validation'],out)
        elif ns.cmd=='authored-patch':
            b=load_session_store(_store(ns),_sid(ns)); out={'candidate_diff':b.get(AUTHOR_STORE_FILES['diff']),'file_edits':b.get(AUTHOR_STORE_FILES['file_edits']),'test_edits':b.get(AUTHOR_STORE_FILES['test_edits']),'repository_modified':False,'change_package_created':False}
        elif ns.cmd in {'review-authored-patch','reject-authored-patch'}:
            b=load_session_store(_store(ns),_sid(ns)); raw=_load(ns.json_file); raw['decision']='rejected' if ns.cmd=='reject-authored-patch' else raw.get('decision','confirmed'); out=review_authored_patch(b[AUTHOR_STORE_FILES['diff']],b[AUTHOR_STORE_FILES['file_edits']],b[AUTHOR_STORE_FILES['test_edits']],b[AUTHOR_STORE_FILES['validation']],raw); write_session_artifact(_store(ns),_sid(ns),AUTHOR_STORE_FILES['review'],out)
        elif ns.cmd=='revise-authored-patch':
            b=load_session_store(_store(ns),_sid(ns)); review=b.get(AUTHOR_STORE_FILES['review'],{}); raw=_load(ns.json_file)
            if review.get('decision')!='requires_revision': raise ValueError('authored_patch_revision_not_requested')
            definitions=raw.get('definitions',[]) if isinstance(raw,dict) else raw; files,tests=author_file_edits(b[AUTHOR_STORE_FILES['intake']],b[REPAIR_STORE_FILES['patch']],b[AUTHOR_STORE_FILES['snapshots']],definitions,previous_candidate_reference=_ref(b[AUTHOR_STORE_FILES['diff']])); out=build_candidate_diff(b[AUTHOR_STORE_FILES['intake']],b[AUTHOR_STORE_FILES['snapshots']],files,tests,previous_candidate_reference=_ref(b[AUTHOR_STORE_FILES['diff']])); write_session_artifact(_store(ns),_sid(ns),AUTHOR_STORE_FILES['file_edits'],files); write_session_artifact(_store(ns),_sid(ns),AUTHOR_STORE_FILES['test_edits'],tests); write_session_artifact(_store(ns),_sid(ns),AUTHOR_STORE_FILES['diff'],out)
        elif ns.cmd=='prepare-change-package':
            b=load_session_store(_store(ns),_sid(ns)); intake=b[AUTHOR_STORE_FILES['intake']]
            prep=build_change_package_preparation(work_request=b.get('work-entry/request.json',{}),human_plan_confirmation=b.get('planning/multifile-change-plan-confirmation.json',{}),reproduction_result=b.get(REPRO_STORE_FILES['result'],{}),repair_strategy=b[REPAIR_STORE_FILES['strategy']],patch_candidate=b[REPAIR_STORE_FILES['patch']],human_patch_review=b[REPAIR_STORE_FILES['review']],authoring_intake=intake,candidate_diff=b[AUTHOR_STORE_FILES['diff']],authoring_validation=b[AUTHOR_STORE_FILES['validation']],human_authored_patch_review=b[AUTHOR_STORE_FILES['review']],source_snapshots=b[AUTHOR_STORE_FILES['snapshots']],repository_identity=intake.get('repository_identity',{}),workspace_snapshot_reference=intake.get('workspace_snapshot_reference',{}),confirmed_scope=intake.get('confirmed_scope',[]),iteration_reference=intake.get('iteration_reference',{}),session_id=_sid(ns))
            out=build_change_package_candidate(prep,intake,b[AUTHOR_STORE_FILES['snapshots']],b[AUTHOR_STORE_FILES['file_edits']],b[AUTHOR_STORE_FILES['test_edits']],b[AUTHOR_STORE_FILES['diff']],b[REPAIR_STORE_FILES['patch']]); write_session_artifact(_store(ns),_sid(ns),AUTHZ_STORE_FILES['preparation'],prep); write_session_artifact(_store(ns),_sid(ns),AUTHZ_STORE_FILES['candidate'],out)
        elif ns.cmd in {'review-change-package','reject-change-package'}:
            b=load_session_store(_store(ns),_sid(ns)); raw=_load(ns.json_file); raw['decision']='rejected' if ns.cmd=='reject-change-package' else raw.get('decision','approved'); out=review_change_package(b[AUTHZ_STORE_FILES['candidate']],b[AUTHZ_STORE_FILES['validation']],raw); write_session_artifact(_store(ns),_sid(ns),AUTHZ_STORE_FILES['approval'],out)
        elif ns.cmd=='revise-change-package':
            b=load_session_store(_store(ns),_sid(ns)); out=revise_change_package_candidate(b[AUTHZ_STORE_FILES['candidate']],_load(ns.json_file)); write_session_artifact(_store(ns),_sid(ns),AUTHZ_STORE_FILES['candidate'],out)
        elif ns.cmd=='build-patch-authorization-request':
            b=load_session_store(_store(ns),_sid(ns)); out=build_authorization_request(b[AUTHZ_STORE_FILES['candidate']],b[AUTHZ_STORE_FILES['approval']]); write_session_artifact(_store(ns),_sid(ns),AUTHZ_STORE_FILES['request'],out)
        elif ns.cmd in {'authorize-patch','reject-patch-authorization'}:
            b=load_session_store(_store(ns),_sid(ns)); raw=_load(ns.json_file); raw['decision']='rejected' if ns.cmd=='reject-patch-authorization' else raw.get('decision','authorized'); out=decide_patch_authorization(b[AUTHZ_STORE_FILES['request']],b[AUTHZ_STORE_FILES['candidate']],b[AUTHZ_STORE_FILES['approval']],raw); write_session_artifact(_store(ns),_sid(ns),AUTHZ_STORE_FILES['decision'],out)
        elif ns.cmd=='authorized-change-package':
            b=load_session_store(_store(ns),_sid(ns)); out=build_authorized_change_package(b[AUTHZ_STORE_FILES['candidate']],b[AUTHZ_STORE_FILES['approval']],b[AUTHZ_STORE_FILES['decision']]); write_session_artifact(_store(ns),_sid(ns),AUTHZ_STORE_FILES['authorized'],out)
        elif ns.cmd=='verify-patch-readiness':
            b=load_session_store(_store(ns),_sid(ns)); out=verify_patch_readiness(b[AUTHZ_STORE_FILES['authorized']],b[AUTHZ_STORE_FILES['candidate']],b[AUTHZ_STORE_FILES['approval']],b[AUTHZ_STORE_FILES['decision']],source_snapshots=b[AUTHOR_STORE_FILES['snapshots']],authoring_intake=b[AUTHOR_STORE_FILES['intake']],patch_candidate=b[REPAIR_STORE_FILES['patch']],workspace_root=ns.workspace_root); write_session_artifact(_store(ns),_sid(ns),AUTHZ_STORE_FILES['readiness'],out)
        elif ns.cmd in {'build-explicit-apply-request','confirm-explicit-apply','reject-explicit-apply'}:
            b=load_session_store(_store(ns),_sid(ns)); raw=_load(ns.json_file)
            if ns.cmd=='confirm-explicit-apply': raw['decision']='confirmed'
            elif ns.cmd=='reject-explicit-apply': raw['decision']='rejected'
            out=build_explicit_apply_request(b[AUTHZ_STORE_FILES['authorized']],b[AUTHZ_STORE_FILES['readiness']],b[AUTHZ_STORE_FILES['approval']],b[AUTHZ_STORE_FILES['decision']],raw); write_session_artifact(_store(ns),_sid(ns),APPLY_STORE_FILES['request'],out)
        elif ns.cmd=='admit-patch-apply':
            b=load_session_store(_store(ns),_sid(ns)); out=admit_patch_apply(b[APPLY_STORE_FILES['request']],b[AUTHZ_STORE_FILES['authorized']],b[AUTHZ_STORE_FILES['readiness']],b[AUTHZ_STORE_FILES['candidate']],b[AUTHZ_STORE_FILES['approval']],b[AUTHZ_STORE_FILES['decision']],source_snapshots=b[AUTHOR_STORE_FILES['snapshots']],authoring_intake=b[AUTHOR_STORE_FILES['intake']],patch_candidate=b[REPAIR_STORE_FILES['patch']],workspace_root=ns.workspace_root); write_session_artifact(_store(ns),_sid(ns),APPLY_STORE_FILES['admission'],out)
            if out.get('admission_status')=='admitted': usage=reserve_authorization(out,b[AUTHZ_STORE_FILES['authorized']],b[AUTHZ_STORE_FILES['decision']]); write_session_artifact(_store(ns),_sid(ns),APPLY_STORE_FILES['usage'],usage)
        elif ns.cmd=='apply-authorized-patch':
            b=load_session_store(_store(ns),_sid(ns)); tx,evidence,usage,out=apply_authorized_patch(b[APPLY_STORE_FILES['admission']],b[APPLY_STORE_FILES['usage']],b[AUTHZ_STORE_FILES['authorized']],b[AUTHZ_STORE_FILES['candidate']],workspace_root=ns.workspace_root); write_session_artifact(_store(ns),_sid(ns),APPLY_STORE_FILES['transaction'],tx); write_session_artifact(_store(ns),_sid(ns),APPLY_STORE_FILES['evidence'],{'operations':evidence}); write_session_artifact(_store(ns),_sid(ns),APPLY_STORE_FILES['usage'],usage); write_session_artifact(_store(ns),_sid(ns),APPLY_STORE_FILES['result'],out)
        elif ns.cmd=='patch-apply-result': out=load_session_store(_store(ns),_sid(ns)).get(APPLY_STORE_FILES['result'],{'mutation_status':'not_started'})
        elif ns.cmd=='verify-applied-patch':
            b=load_session_store(_store(ns),_sid(ns)); tests,out=verify_applied_patch(b[APPLY_STORE_FILES['result']],b[AUTHZ_STORE_FILES['candidate']],workspace_root=ns.workspace_root); write_session_artifact(_store(ns),_sid(ns),APPLY_STORE_FILES['verification'],out)
        elif ns.cmd=='patch-verification-result': out=load_session_store(_store(ns),_sid(ns)).get(APPLY_STORE_FILES['verification'],{'verification_status':'not_started'})
        elif ns.cmd=='completion-review-candidate':
            b=load_session_store(_store(ns),_sid(ns)); out=build_completion_review_candidate(b[APPLY_STORE_FILES['result']],b[APPLY_STORE_FILES['verification']],b.get(APPLY_STORE_FILES['evidence'],{}).get('operations',[])); write_session_artifact(_store(ns),_sid(ns),APPLY_STORE_FILES['completion'],out)
        elif ns.cmd=='review-completion':
            b=load_session_store(_store(ns),_sid(ns)); out=review_completion(b[APPLY_STORE_FILES['completion']],_load(ns.json_file)); write_session_artifact(_store(ns),_sid(ns),APPLY_STORE_FILES['review'],out)
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
            bundle=load_session_store(_store(ns), _sid(ns))
            if bundle.get(AUTHZ_STORE_FILES['candidate']):
                intake=bundle.get(AUTHOR_STORE_FILES['intake'],{}); out=validate_change_package_candidate(bundle[AUTHZ_STORE_FILES['candidate']],preparation=bundle.get(AUTHZ_STORE_FILES['preparation']),candidate_diff=bundle.get(AUTHOR_STORE_FILES['diff']),source_snapshots=bundle.get(AUTHOR_STORE_FILES['snapshots']),file_edits=bundle.get(AUTHOR_STORE_FILES['file_edits']),test_edits=bundle.get(AUTHOR_STORE_FILES['test_edits']),human_authored_patch_review=bundle.get(AUTHOR_STORE_FILES['review']),patch_candidate=bundle.get(REPAIR_STORE_FILES['patch']),authoring_intake=intake,repository_identity=intake.get('repository_identity'),session_id=_sid(ns),iteration_reference=intake.get('iteration_reference')); write_session_artifact(_store(ns),_sid(ns),AUTHZ_STORE_FILES['validation'],out)
            else: out=validate_governed_change_package(bundle['work-entry/governed-change-package.json'])
        elif ns.cmd=='change-package':
            bundle=load_session_store(_store(ns), _sid(ns)); pkg=bundle.get(AUTHZ_STORE_FILES['candidate'])
            if pkg: out={'change_package':pkg,'execution_status':'not_started','repository_modified':False,'authorization_granted':False}
            else: pkg=bundle['work-entry/governed-change-package.json']; out={'change_package_id':pkg['change_package_id'],'change_package_fingerprint':pkg['change_package_fingerprint'],'ordered_operations':[{k:o.get(k) for k in ('operation_id','operation_type','target_path','source_path')} for o in pkg['ordered_operations']],'expected_changed_paths':pkg['expected_changed_paths'],'execution_status':'尚未執行','repository_modified':False}
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
