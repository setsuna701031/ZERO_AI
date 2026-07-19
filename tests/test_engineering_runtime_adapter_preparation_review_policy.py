from core.engineering.engineering_runtime_adapter_preparation_review_policy import *
def test_policy_frozen():
 p=build_default_runtime_adapter_preparation_review_policy(); assert p==build_default_runtime_adapter_preparation_review_policy(); assert validate_runtime_adapter_preparation_review_policy(p).valid; assert not validate_runtime_adapter_preparation_review_policy({**p,'requirements':[]}).valid
