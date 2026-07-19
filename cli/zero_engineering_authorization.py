from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from core.engineering.engineering_authorization_intake import build_engineering_authorization_intake
from core.engineering.engineering_authorization_eligibility import build_engineering_authorization_eligibility
from core.engineering.engineering_authorization_policy import build_engineering_authorization_policy
from core.engineering.engineering_authorization_decision import build_engineering_authorization_decision
from core.engineering.engineering_authorization_constraints import build_engineering_authorization_constraints
from core.engineering.engineering_authorization_verification import verify_engineering_authorization
from core.engineering.engineering_authorization_closure import build_engineering_authorization_closure
STAGES=("intake","eligibility","policy","decision","constraints","verification","closure")
def _read(path:str):return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def build_pipeline(approval_closure,intent):
 i=build_engineering_authorization_intake(approval_closure,intent);e=build_engineering_authorization_eligibility(i,intent);p=build_engineering_authorization_policy(i,e,intent);d=build_engineering_authorization_decision(i,e,p);c=build_engineering_authorization_constraints(i,intent);v=verify_engineering_authorization(d,c);x=build_engineering_authorization_closure(i,e,p,d,c,v);return {"intake":i,"eligibility":e,"policy":p,"decision":d,"constraints":c,"verification":v,"closure":x}
def build_parser():
 p=argparse.ArgumentParser();p.add_argument("engineering_approval_closure_json");p.add_argument("--intent");p.add_argument("--stage",choices=STAGES,default="closure");return p
def run(argv=None):
 try:a=build_parser().parse_args(argv)
 except SystemExit as e:return {"error":"argument_error"},int(e.code or 2)
 try:
  artifacts=build_pipeline(_read(a.engineering_approval_closure_json),_read(a.intent) if a.intent else {});return artifacts[a.stage],0 if artifacts["verification"]["status"]=="verified" else 1
 except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):return {"error":"input_error"},2
def main(argv=None):
 value,code=run(argv);sys.stdout.write(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n");return code
if __name__=="__main__":raise SystemExit(main())
__all__=["STAGES","build_parser","build_pipeline","main","run"]
