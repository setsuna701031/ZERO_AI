from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from core.engineering.engineering_proposal_intake import build_engineering_proposal_intake
from core.engineering.engineering_proposal_scope import build_engineering_proposal_scope
from core.engineering.engineering_proposed_change_set import build_engineering_proposed_change_set
from core.engineering.engineering_proposal_dependency_mapping import build_engineering_proposal_dependency_mapping
from core.engineering.engineering_proposal_validation_plan import build_engineering_proposal_validation_plan
from core.engineering.engineering_proposal_risk_review import build_engineering_proposal_risk_review
from core.engineering.engineering_proposal import build_engineering_proposal
from core.engineering.engineering_proposal_verification import verify_engineering_proposal
from core.engineering.engineering_proposal_closure import build_engineering_proposal_closure
STAGES=("intake","scope","changes","dependencies","validation","risks","proposal","verification","closure")
def _read(path):return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def build_parser():
 p=argparse.ArgumentParser();p.add_argument("planning_closure_json");p.add_argument("--intent");p.add_argument("--stage",choices=STAGES,default="closure");return p
def run(argv=None):
 try:a=build_parser().parse_args(argv)
 except SystemExit as e:return {"error":"argument_error"},int(e.code or 2)
 try:
  closure=_read(a.planning_closure_json);intent=_read(a.intent) if a.intent else {};intake=build_engineering_proposal_intake(closure,intent);scope=build_engineering_proposal_scope(intake,intent);changes=build_engineering_proposed_change_set(scope,intent);dependencies=build_engineering_proposal_dependency_mapping(changes,intent.get("dependency_edges"));validation=build_engineering_proposal_validation_plan(changes,intent);risks=build_engineering_proposal_risk_review(changes,intake["evidence_references"],intent);proposal=build_engineering_proposal(intake,scope,changes,dependencies,validation,risks);verification=verify_engineering_proposal(proposal);closure_out=build_engineering_proposal_closure(proposal,verification);artifacts={"intake":intake,"scope":scope,"changes":changes,"dependencies":dependencies,"validation":validation,"risks":risks,"proposal":proposal,"verification":verification,"closure":closure_out};return artifacts[a.stage],0 if verification["status"]=="verified" else 1
 except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):return {"error":"input_error"},2
def main(argv=None):
 value,code=run(argv);sys.stdout.write(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n");return code
if __name__=="__main__":raise SystemExit(main())
__all__=["STAGES","build_parser","main","run"]
