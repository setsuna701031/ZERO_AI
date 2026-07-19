from copy import deepcopy
from core.engineering.engineering_proposal_verification import verify_engineering_proposal
from core.engineering.engineering_proposal import build_engineering_proposal
from core.engineering.engineering_proposal_common import fingerprint,stable_proposal_id
from tests.test_engineering_proposal_closure import proposal_pipeline
def test_verification_success_blocked_and_tamper(tmp_path):
 p=proposal_pipeline(tmp_path)[0];assert verify_engineering_proposal(p)["status"]=="verified"
 bad=deepcopy(p);bad["validation_plan"]=[];assert verify_engineering_proposal(bad)["status"]=="invalid"
 risk=deepcopy(p["risk_review"][0]);body={k:v for k,v in risk.items() if k not in {"proposal_risk_id","fingerprint"}};body["proposal_blocking"]=True;risk={**body,"proposal_risk_id":stable_proposal_id("engineering-proposal-risk-",body)};risk["fingerprint"]=fingerprint(risk)
 blocked=build_engineering_proposal(p["proposal_intake"],p["proposal_scope"],p["proposed_change_set"],p["dependency_mapping"],p["validation_plan"],[risk]);assert verify_engineering_proposal(blocked)["status"]=="blocked"
