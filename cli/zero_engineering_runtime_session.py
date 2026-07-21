from __future__ import annotations
import argparse, json, sys
from core.engineering.engineering_runtime_orchestrator_common import canonical_json
from core.engineering.engineering_runtime_session_v3 import *
from core.engineering.engineering_runtime_session_v3 import _seal

def _read(path):
    with open(path,"r",encoding="utf-8") as f: return json.load(f)

def run(argv=None):
    p=argparse.ArgumentParser(prog="python -m cli.zero_engineering_runtime_session")
    s=p.add_subparsers(dest="cmd",required=True)
    c=s.add_parser("create"); c.add_argument("--repository-identity",required=True); c.add_argument("--task-identity",required=True); c.add_argument("--store")
    a=s.add_parser("append-cycle"); a.add_argument("--store",required=True); a.add_argument("--session-id",required=True); a.add_argument("--cycle",required=True)
    i=s.add_parser("inspect"); i.add_argument("--store",required=True); i.add_argument("--session-id",required=True)
    r=s.add_parser("resume"); r.add_argument("--store",required=True); r.add_argument("--session-id",required=True)
    v=s.add_parser("verify"); v.add_argument("--store",required=True); v.add_argument("--session-id",required=True)
    cc=s.add_parser("close-cycle"); cc.add_argument("--cycle",required=True)
    cs=s.add_parser("close-session"); cs.add_argument("--store",required=True); cs.add_argument("--session-id",required=True)
    ns=s.add_parser("proposal-candidate"); ns.add_argument("--session",required=True); ns.add_argument("--cycle",required=True); ns.add_argument("--verification-reference",required=True); ns.add_argument("--feedback-reference",required=True); ns.add_argument("--objective",required=True); ns.add_argument("--scope",action="append",default=[])
    args=p.parse_args(argv)
    try:
        if args.cmd=="create":
            out=create_engineering_runtime_session(_read(args.repository_identity),_read(args.task_identity))
            if args.store: RuntimeSessionStore(args.store).create(out)
            return out,0
        if args.cmd=="append-cycle":
            store=RuntimeSessionStore(args.store); data=store.load(args.session_id); out=append_engineering_runtime_cycle(data["session"],_read(args.cycle)); store._write(store._base(args.session_id)/"session.json",out,overwrite=True); store.save_cycle(_read(args.cycle)); return out,0
        if args.cmd=="inspect":
            d=RuntimeSessionStore(args.store).load(args.session_id); return inspect_engineering_runtime_session(d["session"],d["cycles"],d["checkpoint"]),0
        if args.cmd=="resume":
            d=RuntimeSessionStore(args.store).load(args.session_id); return resume_decision(d["session"],d["cycles"],d["checkpoint"]),0
        if args.cmd=="verify":
            d=RuntimeSessionStore(args.store).load(args.session_id); validate_engineering_runtime_session(d["session"]); [validate_cycle_linkage({**d["session"],"cycle_references":d["session"].get("cycle_references",[])[:n-1],"cycle_lineage_debug":[]},c) for n,c in enumerate(d["cycles"],1)]; return {"valid":True},0
        if args.cmd=="close-cycle":
            cyc=dict(_read(args.cycle)); body={k:v for k,v in cyc.items() if k not in {"cycle_fingerprint","cycle_id"}}; body["cycle_status"]="closed"; out=_seal(body,"cycle_fingerprint","cycle_id","engineering-runtime-cycle-"); return out,0
        if args.cmd=="close-session":
            store=RuntimeSessionStore(args.store); d=store.load(args.session_id); out=close_engineering_runtime_session(d["session"]); store._write(store._base(args.session_id)/"session.json",out,overwrite=True); return out,0
        if args.cmd=="proposal-candidate":
            return build_proposal_candidate(_read(args.session),_read(args.cycle),_read(args.verification_reference),_read(args.feedback_reference),objective=args.objective,bounded_scope=args.scope),0
    except RuntimeSessionError as exc:
        return {"error":str(exc)},2
    except FileNotFoundError:
        return {"error":"session_or_input_not_found"},2

def main(argv=None):
    out,code=run(argv); sys.stdout.write(canonical_json(out)+"\n"); return code
if __name__=="__main__": raise SystemExit(main())
