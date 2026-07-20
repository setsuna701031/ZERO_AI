from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.engineering.engineering_runtime_orchestrator_common import canonical_json,SCHEMAS
from core.engineering.engineering_runtime_orchestrator import orchestrate_engineering_runtime
from core.engineering.engineering_runtime_session_store import load_session_store
from core.engineering.engineering_runtime_resume import determine_resume
ACTIONS=("request","admission","session","phase","preview","analyze","propose","prepare","authorize","transaction","execute","resume","checkpoint","result","verify","evidence","closure","inspect","pipeline")
def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument("action",choices=ACTIONS); ap.add_argument("--json",default="{}"); ap.add_argument("--workspace-root"); ap.add_argument("--session-root"); ap.add_argument("--execute",action="store_true"); ns=ap.parse_args(argv)
    try:
        p=json.loads(ns.json); action=ns.action
        if action=="inspect": out={"schemas":SCHEMAS,"actions":list(ACTIONS),"default_pipeline_mode":"preview","execution_enabled_by_default":False}
        elif action=="resume":
            if not ns.session_root or not p.get("session_id"): out={"error":{"code":"persisted_session_required"}}
            else: out=determine_resume(load_session_store(ns.session_root,p["session_id"]),p.get("workspace_identity",{}),p.get("artifacts",[]))
        else:
            req=p.setdefault("request",{}) if "request" in p else p; req.setdefault("requested_orchestration_mode","preview" if action=="pipeline" else action if action in ("preview","analyze","propose","prepare","authorize","execute") else "preview")
            out=orchestrate_engineering_runtime(p,p.get("workspace_identity"),ns.workspace_root,ns.execute,p.get("execute_confirmed",False)); out=out.get(action,out) if action not in ("pipeline","preview","analyze","propose","prepare","authorize","transaction","execute") else out
        print(canonical_json(out)); return 2 if "error" in out else 0
    except Exception: print(canonical_json({"error":{"code":"invalid_request"}})); return 2
if __name__=="__main__": raise SystemExit(main())
