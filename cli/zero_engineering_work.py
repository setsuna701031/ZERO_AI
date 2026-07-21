from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from core.engineering.engineering_work_entry import *
from core.engineering.engineering_runtime_orchestrator_common import canonical_json

def _load(p):
    with open(p, encoding='utf-8') as f: return json.load(f)
def _dump(x):
    sys.stdout.write(canonical_json(x)+"\n")

def main(argv=None):
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest='cmd', required=True)
    s=sub.add_parser('submit'); s.add_argument('--statement', required=True); s.add_argument('--repo-id', required=True); s.add_argument('--repo-root', default='.'); s.add_argument('--scope', action='append', required=True); s.add_argument('--mode', default='governed_delivery')
    for c in ('prepare','inspect','resume','human-gate'):
        x=sub.add_parser(c); x.add_argument('coordination_json')
    a=sub.add_parser('attach-artifact'); a.add_argument('coordination_json'); a.add_argument('artifact_json'); a.add_argument('--artifact-key', required=True)
    cont=sub.add_parser('continue'); cont.add_argument('coordination_json'); cont.add_argument('artifact_json'); cont.add_argument('--artifact-key', required=True)
    v=sub.add_parser('verify'); v.add_argument('coordination_json')
    ns=p.parse_args(argv)
    try:
        if ns.cmd=='submit':
            r=create_engineering_work_request(request_statement=ns.statement,repository_identity={'repository_id':ns.repo_id},repository_root_reference=ns.repo_root,requested_scope=ns.scope,requested_mode=ns.mode); i=admit_engineering_work(r); c=create_work_coordination(r,i); out={'work_request':r,'work_intake':i,'coordination':c}
        elif ns.cmd=='prepare':
            c=_load(ns.coordination_json); out={'coordination':c,'decision':resume_work_coordination(c),'prepared_to':'human_gate_or_missing_artifact','mutation_authority_granted':False}
        elif ns.cmd=='inspect': out=inspect_work_coordination(_load(ns.coordination_json))
        elif ns.cmd=='resume': out=resume_work_coordination(_load(ns.coordination_json))
        elif ns.cmd=='human-gate': out=create_human_gate_handoff(_load(ns.coordination_json))
        elif ns.cmd in {'attach-artifact','continue'}: out=advance_work_coordination(_load(ns.coordination_json), _load(ns.artifact_json), ns.artifact_key)
        elif ns.cmd=='verify': out={'valid':True,'inspection':inspect_work_coordination(_load(ns.coordination_json))}
        else: out={'valid':False}
        _dump(out); return 0
    except WorkEntryError as e:
        _dump({'valid':False,'error':e.code}); return 2
    except Exception as e:
        _dump({'valid':False,'error':str(e)}); return 3
if __name__=='__main__': raise SystemExit(main())
