from __future__ import annotations

import argparse, json, sys
from pathlib import Path
from typing import Any

from core.runtime.runtime_mission_model import build_mission_evidence, load_mission
from core.runtime.runtime_mission_orchestrator import (advance_mission, cancel_mission, confirm_mission_plan, create_mission,
    submit_mission_input)

WAITING={"created","planning","waiting_for_plan_confirmation","ready","running","waiting_for_operator","partially_completed","blocked","cancelled"}
def _json(path: Any) -> Any:
    try:return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError,UnicodeError,json.JSONDecodeError) as exc:raise ValueError("invalid_input_json") from exc
def _print(value: Any) -> None: print(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2))
def _roots(args: argparse.Namespace) -> dict[str,Any]: return {"target_root":args.target_root,"workspace_root":args.workspace_root}
def _exit(mission: dict[str,Any]) -> int:
    status=mission.get("mission_status")
    if status=="expired":return 5
    if status=="failed" and any(bool((g.get("failure") or {}).get("critical")) for g in mission.get("goals",{}).values()):return 3
    return 1 if status in WAITING else 0
def _summary(mission: dict[str,Any]) -> dict[str,Any]:
    return {"mission_id":mission.get("mission_id"),"mission_status":mission.get("mission_status"),"goal_counts":{name:len(mission.get(field,[])) for name,field in (("ready","ready_goal_ids"),("running","running_goal_ids"),("waiting","waiting_goal_ids"),("completed","completed_goal_ids"),("failed","failed_goal_ids"),("blocked","blocked_goal_ids"),("cancelled","cancelled_goal_ids"))},"ready_goals":mission.get("ready_goal_ids",[]),"next_required_action":"confirm_goal_plan" if mission.get("mission_status")=="waiting_for_plan_confirmation" else ("session_operator_input" if mission.get("waiting_goal_ids") else "advance_mission"),"completed_percentage":round(100*len(mission.get("completed_goal_ids",[]))/max(1,len(mission.get("goals",{}))),2)}

def parser() -> argparse.ArgumentParser:
    p=argparse.ArgumentParser(prog="zero-mission-runtime"); sub=p.add_subparsers(dest="command",required=True)
    c=sub.add_parser("create"); c.add_argument("mission_input"); c.add_argument("--goal-plan",required=True); c.add_argument("--target-root",required=True); c.add_argument("--workspace-root",required=True); c.add_argument("--mission-path",required=True); c.add_argument("--scheduler-state",required=True); c.add_argument("--now")
    c=sub.add_parser("create-natural");c.add_argument("mission_text");c.add_argument("--operator-id",required=True);c.add_argument("--target-root",required=True);c.add_argument("--workspace-root",required=True);c.add_argument("--requested-scope",action="append",default=[]);c.add_argument("--excluded-scope",action="append",default=[]);c.add_argument("--mission-path",required=True);c.add_argument("--scheduler-state",required=True);c.add_argument("--now")
    for name in ("status","goals","ready","evidence","planning-status","replanning-history"):
        q=sub.add_parser(name); q.add_argument("mission")
    for name in ("confirm-plan","submit-input"):
        q=sub.add_parser(name); q.add_argument("mission"); q.add_argument("operator_input"); q.add_argument("--scheduler-state",required=True); q.add_argument("--now"); q.add_argument("--target-root"); q.add_argument("--workspace-root")
    q=sub.add_parser("advance"); q.add_argument("mission"); q.add_argument("--scheduler-state",required=True); q.add_argument("--target-root",required=True); q.add_argument("--workspace-root",required=True); q.add_argument("--now")
    q=sub.add_parser("cancel"); q.add_argument("mission"); q.add_argument("--operator-id",required=True); q.add_argument("--now")
    for name in ("submit-clarification","request-replan","confirm-replan","reject-replan"):
        q=sub.add_parser(name);q.add_argument("mission");q.add_argument("operator_input");q.add_argument("--scheduler-state");q.add_argument("--now")
    return p

def main(argv: list[str]|None=None) -> int:
    args=parser().parse_args(argv)
    try:
        if args.command=="create": result=create_mission(_json(args.mission_input),goal_plan=_json(args.goal_plan),target_root=args.target_root,workspace_root=args.workspace_root,mission_path=args.mission_path,scheduler_state_path=args.scheduler_state,now=args.now)
        elif args.command=="create-natural":
            from core.runtime.runtime_natural_mission_planner import create_mission_from_planner_output,create_natural_mission_input,plan_natural_mission,save_planner_artifact
            natural=create_natural_mission_input(args.mission_text,operator_id=args.operator_id,target_root=args.target_root,workspace_root=args.workspace_root,requested_scope=args.requested_scope,excluded_scope=args.excluded_scope,now=args.now);bundle=plan_natural_mission(natural,target_root=args.target_root,workspace_root=args.workspace_root,now=args.now)
            base=Path(args.mission_path);artifact=base.with_suffix(".planner.json");save_planner_artifact(bundle,artifact)
            result=create_mission_from_planner_output(natural,bundle["planner_output"],planning_request=bundle["planning_request"],target_root=args.target_root,workspace_root=args.workspace_root,mission_path=args.mission_path,scheduler_state_path=args.scheduler_state,now=args.now,planner_output_path=artifact)
        else:
            result=load_mission(args.mission,check_expiry=False)
            if args.command=="status":_print(_summary(result));return 0
            if args.command=="goals":_print(result.get("goals",{}));return 0
            if args.command=="ready":_print(result.get("ready_goal_ids",[]));return 0
            if args.command=="evidence":_print(result.get("mission_evidence") or build_mission_evidence(result));return 0
            if args.command=="planning-status":_print({key:result.get(key) for key in ("planning_status","planning_revision","clarification_required","replan_required","replanning_status","replanning_revision")});return 0
            if args.command=="replanning-history":_print(result.get("replanning_history",[]));return 0
            if args.command=="confirm-plan":result=confirm_mission_plan(result,_json(args.operator_input),scheduler_state=args.scheduler_state,now=args.now)
            elif args.command=="advance":result=advance_mission(result,scheduler_state=args.scheduler_state,now=args.now,runtime_config=_roots(args))
            elif args.command=="submit-input":result=submit_mission_input(result,_json(args.operator_input),scheduler_state=args.scheduler_state,now=args.now,runtime_config=_roots(args))
            elif args.command=="cancel":result=cancel_mission(result,operator_id=args.operator_id,now=args.now)
            elif args.command in {"submit-clarification","request-replan","confirm-replan","reject-replan"}:result=submit_mission_input(result,_json(args.operator_input),scheduler_state=args.scheduler_state,now=args.now)
        _print(_summary(result));return _exit(result)
    except ValueError as exc:
        print(json.dumps({"error":str(exc)},ensure_ascii=False),file=sys.stderr)
        text=str(exc)
        if "expired" in text:return 5
        if any(word in text for word in ("fingerprint","mismatch","transition","cycle","identity")):return 4
        return 2

if __name__=="__main__":raise SystemExit(main())
