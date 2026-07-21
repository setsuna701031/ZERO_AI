from __future__ import annotations
import argparse, json, sys
from core.engineering.engineering_runtime_orchestrator_common import canonical_json
from core.engineering.engineering_runtime_session_v3 import *
from core.engineering.engineering_runtime_session_v3 import _seal
from core.engineering.engineering_runtime_objectives_v4 import *

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
    do=s.add_parser("define-objectives"); do.add_argument("--store",required=True); do.add_argument("--session-id",required=True); do.add_argument("--input",required=True)
    ao=s.add_parser("assign-cycle-objectives"); ao.add_argument("--store",required=True); ao.add_argument("--session-id",required=True); ao.add_argument("--cycle-number",type=int,required=True); ao.add_argument("--input",required=True)
    ep=s.add_parser("evaluate-progress"); ep.add_argument("--store",required=True); ep.add_argument("--session-id",required=True); ep.add_argument("--cycle-number",type=int,required=True); ep.add_argument("--input",required=True)
    ec=s.add_parser("evaluate-completion"); ec.add_argument("--store",required=True); ec.add_argument("--session-id",required=True)
    eh=s.add_parser("evaluate-iteration-health"); eh.add_argument("--store",required=True); eh.add_argument("--session-id",required=True)
    nc=s.add_parser("create-next-objective-candidate"); nc.add_argument("--store",required=True); nc.add_argument("--session-id",required=True)
    rr=s.add_parser("request-completion-review"); rr.add_argument("--store",required=True); rr.add_argument("--session-id",required=True)
    rd=s.add_parser("record-completion-decision"); rd.add_argument("--store",required=True); rd.add_argument("--session-id",required=True); rd.add_argument("--review-request",required=True); rd.add_argument("--decision",required=True); rd.add_argument("--human-actor",required=True); rd.add_argument("--apply",action="store_true")
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
        if args.cmd=="define-objectives":
            store=RuntimeSessionStore(args.store); d=store.load(args.session_id); x=_read(args.input); objs=[build_session_objective(d["session"], source_task_identity=x.get("source_task_identity",d["session"].get("task_identity",{})), source_planning_reference=x.get("source_planning_reference"), objective_statement=o["objective_statement"], bounded_scope=o["bounded_scope"], acceptance_criteria=o["acceptance_criteria"], required_evidence=o.get("required_evidence",[]), priority=o.get("priority","required"), objective_status=o.get("objective_status","defined")) for o in x.get("objectives",[])]
            [store.save_objective(o) for o in objs]; return {"objectives":objs},0
        if args.cmd=="assign-cycle-objectives":
            store=RuntimeSessionStore(args.store); d=store.load(args.session_id); x=_read(args.input); cyc=[c for c in d["cycles"] if c.get("cycle_number")==args.cycle_number][0]; out=build_cycle_objective_assignment(d["session"],cyc,d["objectives"],target_criteria=x["target_criteria"],declared_scope=x["declared_scope"],excluded_scope=x.get("excluded_scope",[]),expected_evidence=x.get("expected_evidence",[]),previous_progress=d["progress"][-1] if d["progress"] else None); store.save_assignment(out); return out,0
        if args.cmd=="evaluate-progress":
            store=RuntimeSessionStore(args.store); d=store.load(args.session_id); x=_read(args.input); ass=[a for a in d["assignments"] if a.get("cycle_number")==args.cycle_number][0]; out=evaluate_objective_progress(d["session"],d["objectives"],ass,satisfied_evidence=x.get("satisfied_evidence",[]),partial_criteria=x.get("partial_criteria",[]),blocked_criteria=x.get("blocked_criteria",[]),failed_criteria=x.get("failed_criteria",[]),feedback=x.get("feedback"),scope_observations=x.get("scope_observations",[]),verification_failures=x.get("verification_failures",[])); store.save_progress(out); return out,0
        if args.cmd=="evaluate-completion":
            store=RuntimeSessionStore(args.store); d=store.load(args.session_id); out=evaluate_completion_readiness(d["session"],d["objectives"],d["progress"],d["cycles"]); store.save_completion(out); return out,0
        if args.cmd=="evaluate-iteration-health":
            store=RuntimeSessionStore(args.store); d=store.load(args.session_id); out=evaluate_iteration_health(d["session"],d["progress"]); store.save_iteration_health(out); return out,0
        if args.cmd=="create-next-objective-candidate":
            store=RuntimeSessionStore(args.store); d=store.load(args.session_id); out=create_next_iteration_objective_candidate(d["session"],d["progress"][-1],d["objectives"],health=d.get("iteration_health")); store.save_next_objective_candidate(out); return out,0
        if args.cmd=="request-completion-review":
            store=RuntimeSessionStore(args.store); d=store.load(args.session_id); ready=[c for c in d["completion"] if c.get("schema")==READINESS_SCHEMA][-1]; out=request_completion_review(d["session"],ready); store.save_completion(out); return out,0
        if args.cmd=="record-completion-decision":
            store=RuntimeSessionStore(args.store); d=store.load(args.session_id); out=record_completion_decision(d["session"],_read(args.review_request),decision=args.decision,human_actor_reference=json.loads(args.human_actor)); store.save_completion(out);
            if args.apply and out["decision"]=="approved_complete": store._write(store._base(args.session_id)/"session.json",apply_completion_decision(d["session"],out),overwrite=True)
            return out,0
        if args.cmd=="proposal-candidate":
            return build_proposal_candidate(_read(args.session),_read(args.cycle),_read(args.verification_reference),_read(args.feedback_reference),objective=args.objective,bounded_scope=args.scope),0
    except RuntimeSessionError as exc:
        return {"error":str(exc)},2
    except FileNotFoundError:
        return {"error":"session_or_input_not_found"},2

def main(argv=None):
    out,code=run(argv); sys.stdout.write(canonical_json(out)+"\n"); return code
if __name__=="__main__": raise SystemExit(main())
