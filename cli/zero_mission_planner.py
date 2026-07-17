from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from typing import Any
from core.runtime.runtime_mission_model import load_mission,save_mission
from core.runtime.runtime_mission_replanner import create_replanning_request,deterministic_replanner,stage_replan,validate_replanner_output
from core.runtime.runtime_natural_mission_planner import (create_mission_from_planner_output,create_natural_mission_input,load_planner_artifact,plan_natural_mission,save_planner_artifact,validate_planner_output)

def _json(path:Any)->Any:return load_planner_artifact(path)
def _print(v:Any):print(json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2))
def parser()->argparse.ArgumentParser:
 p=argparse.ArgumentParser(prog="zero-mission-planner");s=p.add_subparsers(dest="command",required=True)
 q=s.add_parser("plan");q.add_argument("mission_text");q.add_argument("--operator-id",required=True);q.add_argument("--target-root",required=True);q.add_argument("--workspace-root",required=True);q.add_argument("--requested-scope",action="append",default=[]);q.add_argument("--excluded-scope",action="append",default=[]);q.add_argument("--result-path",required=True);q.add_argument("--now")
 q=s.add_parser("plan-file");q.add_argument("natural_input");q.add_argument("--target-root",required=True);q.add_argument("--workspace-root",required=True);q.add_argument("--result-path",required=True);q.add_argument("--now")
 for name in ("validate","status"):
  q=s.add_parser(name);q.add_argument("planner_output")
 q=s.add_parser("create-mission");q.add_argument("natural_input");q.add_argument("planner_output");q.add_argument("--target-root",required=True);q.add_argument("--workspace-root",required=True);q.add_argument("--mission-path",required=True);q.add_argument("--scheduler-state",required=True);q.add_argument("--now")
 q=s.add_parser("replan");q.add_argument("mission");q.add_argument("replanning_request");q.add_argument("--result-path",required=True);q.add_argument("--now")
 return p
def main(argv:list[str]|None=None)->int:
 args=parser().parse_args(argv)
 try:
  if args.command=="plan":natural=create_natural_mission_input(args.mission_text,operator_id=args.operator_id,target_root=args.target_root,workspace_root=args.workspace_root,requested_scope=args.requested_scope,excluded_scope=args.excluded_scope,now=args.now);bundle=plan_natural_mission(natural,target_root=args.target_root,workspace_root=args.workspace_root,now=args.now);save_planner_artifact(bundle,args.result_path);_print(bundle);return 1 if bundle["planner_output"]["plan_status"]!="planned" else 0
  if args.command=="plan-file":natural=_json(args.natural_input);bundle=plan_natural_mission(natural,target_root=args.target_root,workspace_root=args.workspace_root,now=args.now);save_planner_artifact(bundle,args.result_path);_print(bundle);return 1 if bundle["planner_output"]["plan_status"]!="planned" else 0
  artifact=_json(args.planner_output) if args.command in {"validate","status"} else None
  if args.command in {"validate","status"}:
   output=artifact.get("planner_output",artifact);request=artifact.get("planning_request",{})
   reasons=validate_planner_output(output,request)
   result={"valid":not reasons,"plan_status":output.get("plan_status"),"planner_output_id":output.get("planner_output_id"),"reasons":reasons};_print(result);return 0 if not reasons else 6
  if args.command=="create-mission":
   natural=_json(args.natural_input);bundle=_json(args.planner_output);output=bundle.get("planner_output",bundle);request=bundle.get("planning_request")
   if not request:raise ValueError("planning_request_required")
   mission=create_mission_from_planner_output(natural,output,planning_request=request,target_root=args.target_root,workspace_root=args.workspace_root,mission_path=args.mission_path,scheduler_state_path=args.scheduler_state,now=args.now,planner_output_path=args.planner_output);_print(mission);return 0
  mission=load_mission(args.mission,check_expiry=False);request=_json(args.replanning_request);output=deterministic_replanner(request,mission);reasons=validate_replanner_output(output,request,mission,now=args.now)
  if reasons:raise ValueError(";".join(reasons))
  save_planner_artifact(output,args.result_path);mission=stage_replan(mission,request,output,now=args.now);save_mission(mission,args.mission);_print(output);return 0
 except ValueError as exc:
  text=str(exc);print(json.dumps({"error":text},ensure_ascii=False),file=sys.stderr)
  if "expired" in text:return 5
  if any(x in text for x in ("fingerprint","identity","cycle","transition")):return 4
  if "planner" in text or "scope" in text:return 6
  return 2
if __name__=="__main__":raise SystemExit(main())
__all__=["main","parser"]
