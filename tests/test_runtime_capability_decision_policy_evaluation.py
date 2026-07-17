from core.runtime.runtime_capability_decision_policy_evaluation import build_capability_decision_policy_evaluation as build
from tests.test_runtime_capability_decision_review_eligibility import eligibility
from tests.test_runtime_capability_bounded_decision_review_request import review_request
from tests.test_runtime_capability_decision_readiness_closure import decision_closure
def policy(root,ptype="confirm_observation",effect="none"):r=review_request(root,ptype,effect);return build(__import__("core.runtime.runtime_capability_decision_review_eligibility",fromlist=["build_capability_decision_review_eligibility"]).build_capability_decision_review_eligibility(r,decision_closure(root)),r,decision_closure(root))
def test_fixed_policy_rules(tmp_path):
 (tmp_path/"target.txt").touch();assert policy(tmp_path)["policy_status"]=="approved";assert policy(tmp_path,"request_additional_observation","control_plane_only")["policy_status"]=="approved";assert policy(tmp_path,"accept_no_further_action","control_plane_only")["policy_status"]=="not_approved";assert policy(tmp_path,"prepare_execution_plan_review","future_execution_plan_review")["policy_status"]=="approved"
