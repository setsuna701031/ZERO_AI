from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from core.engineering.engineering_work_entry import *
from core.engineering.engineering_read_only_pipeline import create_read_only_pipeline, run_read_only_pipeline, run_next_read_only_stage, inspect_read_only_pipeline, resume_read_only_pipeline, verify_read_only_pipeline, ReadOnlyPipelineError
from core.engineering.engineering_runtime_orchestrator_common import canonical_json
from core.engineering.engineering_approval_execution_activation import *

def _load(p):
    with open(p, encoding='utf-8') as f: return json.load(f)
def _dump(x):
    sys.stdout.write(canonical_json(x)+"\n")

def main(argv=None):
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest='cmd', required=True)
    s=sub.add_parser('submit'); s.add_argument('--statement', required=True); s.add_argument('--repo-id', required=True); s.add_argument('--repo-root', default='.'); s.add_argument('--scope', action='append', required=True); s.add_argument('--mode', default='governed_delivery'); s.add_argument('--acceptance-intent', default='human_review')
    for c in ('prepare','prepare-next','inspect','resume','human-gate','verify-pipeline'):
        x=sub.add_parser(c); x.add_argument('coordination_json'); x.add_argument('--request-json'); x.add_argument('--intake-json'); x.add_argument('--pipeline-json'); x.add_argument('--repo-root')
    for c in ('attach-approval','authorization-handoff','attach-authorization','prepare-execution','admit-adapter','execute','verify-execution','evaluate-progress','verify-activation'):
        x=sub.add_parser(c); x.add_argument('activation_json'); x.add_argument('--approval-json'); x.add_argument('--authorization-json'); x.add_argument('--handoff-json'); x.add_argument('--preparation-json'); x.add_argument('--admission-json'); x.add_argument('--execution-json'); x.add_argument('--verification-json'); x.add_argument('--workspace-root', default='.')
    a=sub.add_parser('attach-artifact'); a.add_argument('coordination_json'); a.add_argument('artifact_json'); a.add_argument('--artifact-key', required=True)
    cont=sub.add_parser('continue'); cont.add_argument('coordination_json'); cont.add_argument('artifact_json'); cont.add_argument('--artifact-key', required=True)
    v=sub.add_parser('verify'); v.add_argument('coordination_json')
    ns=p.parse_args(argv)
    try:
        if ns.cmd=='submit':
            r=create_engineering_work_request(request_statement=ns.statement,repository_identity={'repository_id':ns.repo_id},repository_root_reference=ns.repo_root,requested_scope=ns.scope,requested_mode=ns.mode,acceptance_intent=ns.acceptance_intent); i=admit_engineering_work(r); c=create_work_coordination(r,i); pl=create_read_only_pipeline(r,i,c); out={'work_request':r,'work_intake':i,'coordination':c,'read_only_pipeline':pl}
        elif ns.cmd in {'prepare','prepare-next'}:
            c=_load(ns.coordination_json); r=_load(ns.request_json); i=_load(ns.intake_json); pl=_load(ns.pipeline_json); out=run_next_read_only_stage(r,i,c,pl,repository_root=ns.repo_root) if ns.cmd=='prepare-next' else run_read_only_pipeline(r,i,c,pl,repository_root=ns.repo_root)
        elif ns.cmd=='inspect':
            c=_load(ns.coordination_json); pl=_load(ns.pipeline_json) if ns.pipeline_json else None; out={**inspect_work_coordination(c), 'read_only_pipeline':inspect_read_only_pipeline(c,pl)}
        elif ns.cmd=='resume':
            c=_load(ns.coordination_json); pl=_load(ns.pipeline_json) if ns.pipeline_json else None; out=resume_read_only_pipeline(c,pl)
        elif ns.cmd=='verify-pipeline':
            out=verify_read_only_pipeline(_load(ns.pipeline_json))
        elif ns.cmd=='verify-activation':
            out=validate_activation(_load(ns.activation_json))
        elif ns.cmd=='attach-approval':
            out=attach_human_approval(_load(ns.activation_json), _load(ns.approval_json))
        elif ns.cmd=='authorization-handoff':
            out=create_authorization_handoff(_load(ns.activation_json), _load(ns.approval_json))
        elif ns.cmd=='attach-authorization':
            out=attach_human_authorization(_load(ns.activation_json), _load(ns.authorization_json), _load(ns.approval_json))
        elif ns.cmd=='prepare-execution':
            prep, act = prepare_execution(_load(ns.activation_json), _load(ns.authorization_json), workspace_root=ns.workspace_root); out={'execution_preparation':prep,'activation':act}
        elif ns.cmd=='admit-adapter':
            adm, act = admit_adapter(_load(ns.activation_json), _load(ns.preparation_json)); out={'adapter_admission':adm,'activation':act}
        elif ns.cmd=='execute':
            res, auth, act = activate_governed_execution(_load(ns.activation_json), _load(ns.authorization_json), _load(ns.preparation_json), _load(ns.admission_json), workspace_root=ns.workspace_root); out={'execution_result':res,'authorization':auth,'activation':act}
        elif ns.cmd=='verify-execution':
            ver, act = verify_execution(_load(ns.activation_json), _load(ns.execution_json)); out={'verification':ver,'activation':act}
        elif ns.cmd=='evaluate-progress':
            prog, act = evaluate_progress(_load(ns.activation_json), _load(ns.verification_json)); out={'progress':prog,'activation':act}
        elif ns.cmd=='human-gate': out=create_human_gate_handoff(_load(ns.coordination_json))
        elif ns.cmd in {'attach-artifact','continue'}: out=advance_work_coordination(_load(ns.coordination_json), _load(ns.artifact_json), ns.artifact_key)
        elif ns.cmd=='verify': out={'valid':True,'inspection':inspect_work_coordination(_load(ns.coordination_json))}
        else: out={'valid':False}
        _dump(out); return 0
    except (WorkEntryError, ReadOnlyPipelineError, ActivationError) as e:
        _dump({'valid':False,'error':e.code}); return 2
    except Exception as e:
        _dump({'valid':False,'error':str(e)}); return 3
if __name__=='__main__': raise SystemExit(main())
