from core.engineering.engineering_runtime_adapter_activation_eligibility_policy import *
def test_policy_frozen_deterministic():
 p=build_default_runtime_adapter_activation_eligibility_policy(); assert validate_runtime_adapter_activation_eligibility_policy(p).valid; assert p==build_default_runtime_adapter_activation_eligibility_policy(); p['frozen']=False; assert not validate_runtime_adapter_activation_eligibility_policy(p).valid
