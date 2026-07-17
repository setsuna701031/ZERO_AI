from core.runtime.runtime_capability_decision_authorization_closure import close_capability_decision_authorization as build
from tests.test_runtime_capability_execution_authority import authority
from tests.test_runtime_capability_bounded_execution_request import request
from tests.test_runtime_capability_observation_evidence_closure import closure as observation_closure
from tests.test_runtime_capability_decision_readiness_closure import decision_closure
from tests.test_runtime_capability_bounded_decision_review_request import review_request
from tests.test_runtime_capability_decision_review_eligibility import eligibility
from tests.test_runtime_capability_decision_policy_evaluation import policy
from tests.test_runtime_capability_decision_authorization import authorization
def authorization_closure(root):return build(authority(),request(),observation_closure(root),decision_closure(root),review_request(root),eligibility(root),policy(root),authorization(root))
def test_complete_chain(tmp_path):
 (tmp_path/"target.txt").touch();x=authorization_closure(tmp_path);assert x["verification_status"]=="verified_closed" and x["closed"] and all(x[n] is False for n in ("execution_completion_claim","mutation_authorization_claim","external_execution_authorization_claim","decision_executed_claim"))
