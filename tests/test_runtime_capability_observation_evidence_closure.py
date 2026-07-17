from core.runtime.runtime_capability_observation_evidence_closure import close_capability_observation_evidence as build
from tests.test_runtime_capability_execution_authority import authority
from tests.test_runtime_capability_bounded_execution_request import request
from tests.test_runtime_capability_executor_bridge_verification_closure import bridge_closure
from tests.test_runtime_capability_read_only_adapter_admission import admission
from tests.test_runtime_capability_bounded_observation_request import observation_request
from tests.test_runtime_capability_safe_target_resolution import resolution
from tests.test_runtime_capability_read_only_observation_result import result
def closure(root):return build(authority(),request(),bridge_closure(),admission(root),observation_request("existence","target.txt",root),resolution(root),result(root))
def test_closure_separates_completion(tmp_path):
 (tmp_path/"target.txt").touch();x=closure(tmp_path);assert x["verification_status"]=="verified_closed" and x["execution_completion_claim"] is False and x["recommended_v1_2_outcome_status"]=="not_completed"
