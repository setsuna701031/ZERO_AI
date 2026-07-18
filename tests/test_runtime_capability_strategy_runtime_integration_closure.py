from copy import deepcopy
from core.runtime.runtime_capability_strategy_runtime_integration_verification import verify_runtime_integration
from core.runtime.runtime_capability_strategy_runtime_integration_closure import close_runtime_integration
from tests.test_runtime_capability_strategy_runtime_integration_verification import chain
def verification():c,d,w=chain();return verify_runtime_integration(c,d,w)
def test_only_verified_chain_closes_deterministically():
 v=verification();a=close_runtime_integration(v);b=close_runtime_integration(deepcopy(v));assert a==b and a["status"]=="closed" and a["boundary"]["runtime_activation"] is False and a["closure_payload"]["passive_integration_payload"]==v["verification_payload"]
def test_invalid_verification_does_not_close():
 v=verification();v["fingerprint"]="bad";assert close_runtime_integration(v)["status"]=="invalid"
