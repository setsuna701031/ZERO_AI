from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from core.engineering.engineering_work_entry import *
from core.engineering.engineering_read_only_pipeline import create_read_only_pipeline, run_read_only_pipeline, run_next_read_only_stage, inspect_read_only_pipeline, resume_read_only_pipeline, verify_read_only_pipeline, ReadOnlyPipelineError
from core.engineering.engineering_runtime_orchestrator_common import canonical_json
from core.engineering.engineering_approval_execution_activation import *
from core.engineering.engineering_operator_flow import build_operator_status, start_operator_flow, prepare_operator_flow, create_demo_activation, preview_execution, human_text, resolve_active_engineering_work

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
    except (WorkEntryError, ReadOnlyPipelineError, ActivationError) as e:
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
    s=sub.add_parser('start'); s.add_argument('statement'); s.add_argument('--repository', default='.'); s.add_argument('--repo-id', default='default'); s.add_argument('--scope', action='append', default=['docs/status.txt']); s.add_argument('--mode', default='governed_delivery'); s.add_argument('--acceptance-intent', default='ZERO engineering flow verified.'); s.add_argument('--prepare', action='store_true')
    for c in ('status','inspect','review','approval-summary','authorization-summary','preview','result','resume','completion-review-summary','verify-flow'): sub.add_parser(c)
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
        if ns.cmd=='start': out=start_operator_flow(ns.statement,store_root=_store(ns),repository=ns.repository,repo_id=ns.repo_id,scope=ns.scope,mode=ns.mode,acceptance_intent=ns.acceptance_intent,prepare=ns.prepare)
        elif ns.cmd in {'status','inspect'}: out=build_operator_status(_store(ns), session_id=_sid(ns))
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
        elif ns.cmd=='preview': out=preview_execution(_store(ns), session_id=_sid(ns))
        elif ns.cmd=='execute':
            if not ns.confirm_execution: out={'valid':False,'error':'execution_confirmation_required','mutation_occurred':False}; _emit(out, ns.format, ns.verbose); return 8
            res=resolve_active_engineering_work(_store(ns), session_id=_sid(ns)); b=res['bundle']; auth=_load(ns.authorization_json) if ns.authorization_json else b['work-entry/authorization.json']; prep=_load(ns.preparation_json) if ns.preparation_json else b['work-entry/execution-preparation.json']; adm=_load(ns.admission_json) if ns.admission_json else b['work-entry/adapter-admission.json']; er,auth2,act=activate_governed_execution(b['work-entry/execution-activation.json'],auth,prep,adm,workspace_root=ns.workspace_root); persist_activation_artifacts(_store(ns),res['session_id'],activation=act,authorization=auth2,execution_result=er); out={'execution_result':er,'authorization':auth2,'activation':act}
        elif ns.cmd=='verify':
            res=resolve_active_engineering_work(_store(ns), session_id=_sid(ns)); b=res['bundle']; er=_load(ns.execution_json) if ns.execution_json else b['work-entry/execution-result.json']; ver,act=verify_execution(b['work-entry/execution-activation.json'],er); persist_activation_artifacts(_store(ns),res['session_id'],activation=act,verification=ver); out={'verification':ver,'activation':act}
        elif ns.cmd=='evaluate-progress':
            res=resolve_active_engineering_work(_store(ns), session_id=_sid(ns)); b=res['bundle']; ver=_load(ns.verification_json) if ns.verification_json else b['work-entry/verification.json']; pr,act=evaluate_progress(b['work-entry/execution-activation.json'],ver); persist_activation_artifacts(_store(ns),res['session_id'],activation=act,progress=pr); out={'progress':pr,'activation':act}
        elif ns.cmd=='result': out={'schema':'zero.engineering.operator_result.v1','status':build_operator_status(_store(ns), session_id=_sid(ns)),'executed':False,'verified':False,'completion_candidate':False,'human_completion_accepted':False,'next_governed_action':'completion-review-summary'}
        elif ns.cmd=='resume':
            st=build_operator_status(_store(ns), session_id=_sid(ns)); out={'schema':'zero.engineering.operator_resume_guidance.v1','canonical_status':st,'guidance':st.get('recommended_command'),'will_auto_execute':False}
        elif ns.cmd=='completion-review-summary': out={'schema':'zero.engineering.completion_review_summary.v1','human_decision_options':['accept_completion','continue_iteration','request_changes','stop'],'not_completion_decision':True,'manual_artifact_required':True,'status':build_operator_status(_store(ns), session_id=_sid(ns))}
        elif ns.cmd=='verify-flow': out={'valid':True,'status':build_operator_status(_store(ns), session_id=_sid(ns))}
        elif ns.cmd=='submit':
            req=create_engineering_work_request(request_statement=ns.statement,repository_identity={'repository_id':ns.repo_id},repository_root_reference=ns.repo_root,requested_scope=['docs/status.txt']); i=admit_engineering_work(req); c=create_work_coordination(req,i); pl=create_read_only_pipeline(req,i,c); out={'work_request':req,'work_intake':i,'coordination':c,'read_only_pipeline':pl}
        else: out={'valid':False,'error':'unsupported_existing_contract'}
        _emit(out, ns.format, ns.verbose); return 0
    except (WorkEntryError, ReadOnlyPipelineError, ActivationError) as e:
        _emit({'valid':False,'error':e.code,'current_phase':'blocked','mutation_occurred':False,'safe_next_action':'resume','recovery_guidance':'請檢查治理產物後重試。'}, ns.format, ns.verbose); return 5
    except Exception as e:
        _emit({'valid':False,'error':str(e),'mutation_occurred':False}, ns.format, ns.verbose); return 6
if __name__=='__main__': raise SystemExit(main())
