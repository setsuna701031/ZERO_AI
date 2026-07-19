from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from core.engineering.engineering_approval_intake import build_engineering_approval_intake
from core.engineering.engineering_approval_eligibility import build_engineering_approval_eligibility
from core.engineering.engineering_approval_policy import build_engineering_approval_policy
from core.engineering.engineering_approval_decision import build_engineering_approval_decision
from core.engineering.engineering_approval_conditions import build_engineering_approval_conditions
from core.engineering.engineering_approval_verification import verify_engineering_approval
from core.engineering.engineering_approval_closure import build_engineering_approval_closure
STAGES=("intake","eligibility","policy","decision","conditions","verification","closure")
def _read(path:str):return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def build_pipeline(review_closure,intent):
 i=build_engineering_approval_intake(review_closure,intent);e=build_engineering_approval_eligibility(i,intent);p=build_engineering_approval_policy(i,e,intent);d=build_engineering_approval_decision(i,e,p);c=build_engineering_approval_conditions(i,intent);v=verify_engineering_approval(d,c);x=build_engineering_approval_closure(i,e,p,d,c,v);return {"intake":i,"eligibility":e,"policy":p,"decision":d,"conditions":c,"verification":v,"closure":x}
def build_parser():
 p=argparse.ArgumentParser();p.add_argument("proposal_review_closure_json");p.add_argument("--intent");p.add_argument("--stage",choices=STAGES,default="closure");return p
def run(argv=None):
 try:a=build_parser().parse_args(argv)
 except SystemExit as e:return {"error":"argument_error"},int(e.code or 2)
 try:
  artifacts=build_pipeline(_read(a.proposal_review_closure_json),_read(a.intent) if a.intent else {});return artifacts[a.stage],0 if artifacts["verification"]["status"]=="verified" else 1
 except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):return {"error":"input_error"},2
def main(argv=None):
 value,code=run(argv);sys.stdout.write(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n");return code
if __name__=="__main__":raise SystemExit(main())
__all__=["STAGES","build_parser","build_pipeline","main","run"]
