from core.runtime.runtime_capability_decision_authorization import build_capability_decision_authorization as build
from tests.test_runtime_capability_decision_policy_evaluation import policy
from tests.test_runtime_capability_decision_review_eligibility import eligibility
from tests.test_runtime_capability_bounded_decision_review_request import review_request
from tests.test_runtime_capability_decision_readiness_closure import decision_closure
def authorization(root):return build(policy(root),eligibility(root),review_request(root),decision_closure(root))
def test_authorization_is_control_plane_only(tmp_path):
 (tmp_path/"target.txt").touch();x=authorization(tmp_path);assert x["authorization_status"]=="authorized" and x["authorized_next_stage"]=="observation_confirmation_closure" and all(v is False for v in x["authorized_permissions"].values()) and x["execution_completion_claim"] is False and x["mutation_authorization_claim"] is False
