from core.engineering.engineering_runtime_adapter_preparation_policy import *
def test_policy():
 p=build_default_runtime_adapter_preparation_policy(); assert p==build_default_runtime_adapter_preparation_policy(); assert validate_runtime_adapter_preparation_policy(p).valid; assert not validate_runtime_adapter_preparation_policy({**p,'requirements':[]}).valid
