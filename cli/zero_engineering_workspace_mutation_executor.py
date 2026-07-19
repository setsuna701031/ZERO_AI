from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.engineering.engineering_governed_workspace_mutation_executor import validate_only,execute_pipeline
from core.engineering.engineering_workspace_mutation_executor_common import canonical_json,SCHEMAS

def emit(o): print(canonical_json(o))
def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('action'); ap.add_argument('--json',default='{}'); ap.add_argument('--workspace-root'); ap.add_argument('--execute',action='store_true'); ns=ap.parse_args(argv)
    try:
        p=json.loads(ns.json or '{}'); handoff=p.get('handoff') or p.get('executor_handoff') or p
        if ns.action in ('inspect','validate'):
            o={'schemas':SCHEMAS,'actions':['root-binding','admission','live-precondition','token-consumption','transaction-store','backup','stage','validate-stage','commit-gate','commit','post-commit-verify','failure','rollback','recovery-verify','result','evidence','closure','validate','inspect','pipeline']}
        elif ns.action=='pipeline':
            o=execute_pipeline(handoff,ns.workspace_root,p.get('execute_confirmed') is True) if ns.execute else validate_only(handoff,ns.workspace_root)
        else:
            o=validate_only(handoff,ns.workspace_root)
        emit(o); return 0 if 'error' not in o else 2
    except Exception:
        emit({'error':{'code':'invalid_request'}}); return 2
if __name__=='__main__': raise SystemExit(main())
