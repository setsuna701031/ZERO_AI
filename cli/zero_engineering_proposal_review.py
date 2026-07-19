from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from core.engineering.engineering_proposal_review_intake import build_engineering_proposal_review_intake
from core.engineering.engineering_proposal_evidence_review import build_engineering_proposal_evidence_review
from core.engineering.engineering_proposal_scope_review import build_engineering_proposal_scope_review
from core.engineering.engineering_proposal_dependency_review import build_engineering_proposal_dependency_review
from core.engineering.engineering_proposal_validation_review import build_engineering_proposal_validation_review
from core.engineering.engineering_proposal_risk_review_assessment import build_engineering_proposal_risk_review_assessment
from core.engineering.engineering_proposal_governance_review import build_engineering_proposal_governance_review
from core.engineering.engineering_proposal_review_findings import build_engineering_proposal_review_findings
from core.engineering.engineering_proposal_review_decision import build_engineering_proposal_review_decision
from core.engineering.engineering_proposal_review import build_engineering_proposal_review
from core.engineering.engineering_proposal_review_verification import verify_engineering_proposal_review
from core.engineering.engineering_proposal_review_closure import build_engineering_proposal_review_closure
STAGES=("intake","evidence","scope","dependencies","validation","risks","governance","findings","decision","review","verification","closure")
def _read(path:str):return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def build_parser():
 p=argparse.ArgumentParser();p.add_argument("proposal_closure_json");p.add_argument("--intent");p.add_argument("--stage",choices=STAGES,default="closure");return p
def build_pipeline(c,i):
 intake=build_engineering_proposal_review_intake(c,i);e=build_engineering_proposal_evidence_review(intake,c,i);s=build_engineering_proposal_scope_review(intake,c,i);d=build_engineering_proposal_dependency_review(intake,c,i);v=build_engineering_proposal_validation_review(intake,c,i);r=build_engineering_proposal_risk_review_assessment(intake,c,i);g=build_engineering_proposal_governance_review(intake,c,i);reviews={"evidence":e,"scope":s,"dependency":d,"validation":v,"risk":r,"governance":g};f=build_engineering_proposal_review_findings(reviews);decision=build_engineering_proposal_review_decision(intake,reviews,f);review=build_engineering_proposal_review(intake,e,s,d,v,r,g,f,decision);verification=verify_engineering_proposal_review(review);closure=build_engineering_proposal_review_closure(review,verification);return {"intake":intake,"evidence":e,"scope":s,"dependencies":d,"validation":v,"risks":r,"governance":g,"findings":f,"decision":decision,"review":review,"verification":verification,"closure":closure}
def run(argv=None):
 try:a=build_parser().parse_args(argv)
 except SystemExit as e:return {"error":"argument_error"},int(e.code or 2)
 try:
  artifacts=build_pipeline(_read(a.proposal_closure_json),_read(a.intent) if a.intent else {});out=artifacts[a.stage];return out,0 if artifacts["verification"]["status"]=="verified" else 1
 except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):return {"error":"input_error"},2
def main(argv=None):
 value,code=run(argv);sys.stdout.write(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n");return code
if __name__=="__main__":raise SystemExit(main())
__all__=["STAGES","build_parser","build_pipeline","main","run"]
