from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.engineering.engineering_runtime_orchestrator_common import canonical_json,SCHEMAS
from core.engineering.engineering_runtime_orchestrator import orchestrate_engineering_runtime
from core.engineering.engineering_runtime_session_store import load_session_store
from core.engineering.engineering_runtime_resume import determine_resume
ACTIONS=("request","capability-admission","admission","session","phase","preview","analyze","propose","prepare","authorize","transaction","execute","resume","checkpoint","result","verify","evidence","closure","inspect","pipeline")
def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument("action",choices=ACTIONS); ap.add_argument("--json",default="{}"); ap.add_argument("--workspace-root"); ap.add_argument("--session-root"); ap.add_argument("--capability-registry"); ap.add_argument("--capability-id"); ap.add_argument("--capability-operation"); ap.add_argument("--adapter-id"); ap.add_argument("--adapter-fingerprint"); ap.add_argument("--execute",action="store_true"); ap.add_argument("--confirm-controlled-execution",action="store_true"); ns=ap.parse_args(argv)
    try:
        p=json.loads(ns.json); action=ns.action
        if action=="inspect": out={"schemas":SCHEMAS,"actions":list(ACTIONS),"default_pipeline_mode":"preview","execution_enabled_by_default":False}
        elif action=="resume":
            if not ns.session_root or not p.get("session_id"): out={"error":{"code":"persisted_session_required"}}
            else: out=determine_resume(load_session_store(ns.session_root,p["session_id"]),p.get("workspace_identity",{}),p.get("artifacts",[]))
        else:
            capability_arguments=(ns.capability_registry,ns.capability_id,ns.capability_operation,ns.adapter_id,ns.adapter_fingerprint)
            if any(value is not None for value in capability_arguments):
                if "request" not in p:
                    p={"request":p}
                if ns.capability_registry:
                    p["capability_registry"]=json.loads(Path(ns.capability_registry).read_text(encoding="utf-8"))
                p.update(requested_capability_id=ns.capability_id,requested_operation=ns.capability_operation,
                         requested_adapter_id=ns.adapter_id,requested_adapter_fingerprint=ns.adapter_fingerprint)
            req=p.setdefault("request",{}) if "request" in p else p; req.setdefault("requested_orchestration_mode","preview" if action=="pipeline" else action if action in ("preview","analyze","propose","prepare","authorize","execute") else "preview")
            confirmed=ns.confirm_controlled_execution and p.get("execute_confirmed") is True
            out=orchestrate_engineering_runtime(p,p.get("workspace_identity"),ns.workspace_root,ns.execute,confirmed); out=out.get(action.replace("-","_"),out) if action not in ("pipeline","preview","analyze","propose","prepare","authorize","transaction","execute") else out
        print(canonical_json(out)); return 2 if "error" in out or out.get("status") in ("invalid","not_admitted","not_registered","inactive","deprecated","ambiguous","adapter_mismatch","operation_unsupported","blocked","invalid_registry","invalid_request") else 0
    except Exception: print(canonical_json({"error":{"code":"invalid_request"}})); return 2
if __name__=="__main__": raise SystemExit(main())
