from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from core.engineering.engineering_planning_context import build_engineering_planning_context
from core.engineering.engineering_goal_extraction import extract_engineering_goals
from core.engineering.engineering_work_breakdown import build_engineering_work_breakdown
from core.engineering.engineering_dependency_ordering import build_engineering_dependency_ordering
from core.engineering.engineering_validation_strategy import build_engineering_validation_strategy
from core.engineering.engineering_risk_assessment import build_engineering_risk_assessment
from core.engineering.engineering_plan import build_engineering_plan
from core.engineering.engineering_planning_verification import verify_engineering_plan
from core.engineering.engineering_planning_closure import build_engineering_planning_closure
STAGES=("context","goals","work-breakdown","dependencies","validation","risks","plan","verification","closure")
def _read(path):return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def build_parser():
 p=argparse.ArgumentParser();p.add_argument("closure_json");p.add_argument("--intent");p.add_argument("--constraints");p.add_argument("--stage",choices=STAGES,default="closure");return p
def run(argv=None):
 try:a=build_parser().parse_args(argv)
 except SystemExit as e:return {"error":"argument_error"},int(e.code or 2)
 try:
  closure=_read(a.closure_json);intent=_read(a.intent) if a.intent else {};constraints=_read(a.constraints) if a.constraints else {}
  context=build_engineering_planning_context(closure,intent,constraints);goals=extract_engineering_goals(context,intent);work=build_engineering_work_breakdown(goals);deps=build_engineering_dependency_ordering(work);validation=build_engineering_validation_strategy(goals,work);risks=build_engineering_risk_assessment(context,goals,work);plan=build_engineering_plan(context,goals,work,deps,validation,risks);verification=verify_engineering_plan(plan);closure_out=build_engineering_planning_closure(plan,verification)
  artifacts={"context":context,"goals":goals,"work-breakdown":work,"dependencies":deps,"validation":validation,"risks":risks,"plan":plan,"verification":verification,"closure":closure_out};value=artifacts[a.stage]
  return value,0 if verification["status"]=="verified" else 1
 except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):return {"error":"input_error"},2
def main(argv=None):
 value,code=run(argv);sys.stdout.write(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n");return code
if __name__=="__main__":raise SystemExit(main())
__all__=["STAGES","build_parser","main","run"]
