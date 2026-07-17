from copy import deepcopy
from core.runtime.runtime_capability_decision_review_eligibility import build_capability_decision_review_eligibility as build
from tests.test_runtime_capability_bounded_decision_review_request import review_request
from tests.test_runtime_capability_decision_readiness_closure import decision_closure
def eligibility(root):return build(review_request(root),decision_closure(root))
def test_eligibility_and_linkage(tmp_path):
 (tmp_path/"target.txt").touch();x=eligibility(tmp_path);assert x["eligibility_status"]=="eligible" and x==eligibility(tmp_path)
 r=deepcopy(review_request(tmp_path));r["decision_readiness_closure_id"]="other";assert build(r,decision_closure(tmp_path))["eligibility_status"]=="invalid"
