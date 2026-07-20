from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.engineering.engineering_mutation_transaction_common import canonical_json
from core.engineering import engineering_task_orchestration as o
from core.engineering.engineering_task_orchestration_resume import resume_task
from core.engineering.engineering_task_artifact_adapter_registry import default_registry
from core.engineering.engineering_task_artifact_compatibility import build_compatibility_report

def emit(v): print(canonical_json(v))
def load_json(text):
    try: return json.loads(text)
    except Exception: raise ValueError('invalid_json')

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument('command')
    ap.add_argument('--repo-root', default='.')
    ap.add_argument('--task-id')
    ap.add_argument('--json', default='{}')
    ap.add_argument('--workspace-root')
    ns=ap.parse_args(argv)
    try:
        p=load_json(ns.json or '{}'); c=ns.command; tid=ns.task_id or p.get('task_id')
        if c=='list-adapters': out={'adapters':default_registry().inventory()}
        elif c=='inspect-adapter': out=default_registry().get(p.get('adapter_id')).descriptor.as_dict()
        elif c=='compatibility-report': out=build_compatibility_report()
        elif c=='validate-artifact': out=dict(default_registry().validate_artifact(p.get('phase'), p.get('artifact')))
        elif c=='create': out=o.create_task(ns.repo_root,p)
        elif c=='inspect': out=o.inspect_task(ns.repo_root,tid)
        elif c=='admit': out=o.admit_task(ns.repo_root,tid)
        elif c=='attach-analysis': out=o.attach_analysis(ns.repo_root,tid,p)
        elif c=='attach-candidate': out=o.attach_candidate_selection(ns.repo_root,tid,p)
        elif c=='attach-plan': out=o.attach_plan(ns.repo_root,tid,p)
        elif c=='attach-proposal': out=o.attach_proposal(ns.repo_root,tid,p)
        elif c=='attach-approval': out=o.attach_human_approval(ns.repo_root,tid,p)
        elif c=='attach-authorization': out=o.attach_authorization(ns.repo_root,tid,p)
        elif c=='attach-preparation': out=o.attach_preparation(ns.repo_root,tid,p)
        elif c=='attach-token': out=o.attach_authorization_token(ns.repo_root,tid,p)
        elif c=='execute': out=o.execute_task(ns.repo_root,tid,p['handoff'],ns.workspace_root or p['workspace_root'])
        elif c=='attach-verification': out=o.attach_verification(ns.repo_root,tid,p)
        elif c=='close': out=o.close_task(ns.repo_root,tid)
        elif c=='resume': out=resume_task(ns.repo_root,tid)
        else: out={'error':{'code':'unknown_command'}}
        emit(out); return 0 if 'error' not in out else 2
    except Exception as exc:
        emit({'error':{'code':str(exc) or 'invalid_request'}}); return 2
if __name__=='__main__': raise SystemExit(main())
