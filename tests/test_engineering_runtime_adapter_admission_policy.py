from core.engineering.engineering_runtime_adapter_admission_policy import *
def test_policy_valid_and_deterministic():
 p=build_default_runtime_adapter_admission_policy(); assert p==build_default_runtime_adapter_admission_policy(); assert validate_runtime_adapter_admission_policy(p).valid; assert inspect_runtime_adapter_admission_policy(p)['valid']
def test_policy_rejects_mutation():
 p=build_default_runtime_adapter_admission_policy(); p['rules']=[]; assert not validate_runtime_adapter_admission_policy(p).valid
