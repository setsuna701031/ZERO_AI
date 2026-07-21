from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from core.engineering.engineering_work_entry import *
from core.engineering.engineering_read_only_pipeline import create_read_only_pipeline, run_read_only_pipeline, run_next_read_only_stage, inspect_read_only_pipeline, resume_read_only_pipeline, verify_read_only_pipeline, ReadOnlyPipelineError
from core.engineering.engineering_runtime_orchestrator_common import canonical_json

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
        elif ns.cmd=='human-gate': out=create_human_gate_handoff(_load(ns.coordination_json))
        elif ns.cmd in {'attach-artifact','continue'}: out=advance_work_coordination(_load(ns.coordination_json), _load(ns.artifact_json), ns.artifact_key)
        elif ns.cmd=='verify': out={'valid':True,'inspection':inspect_work_coordination(_load(ns.coordination_json))}
        else: out={'valid':False}
        _dump(out); return 0
    except (WorkEntryError, ReadOnlyPipelineError) as e:
        _dump({'valid':False,'error':e.code}); return 2
    except Exception as e:
        _dump({'valid':False,'error':str(e)}); return 3
if __name__=='__main__': raise SystemExit(main())
