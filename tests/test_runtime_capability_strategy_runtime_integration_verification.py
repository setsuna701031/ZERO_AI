from core.runtime.runtime_capability_strategy_runtime_integration_wiring import wire_runtime_integration
from core.runtime.runtime_capability_strategy_runtime_integration_verification import verify_runtime_integration
from tests.test_runtime_capability_strategy_runtime_integration_decision import configuration
from tests.test_runtime_capability_strategy_runtime_integration_wiring import decision
def chain():
 c=configuration();from core.runtime.runtime_capability_strategy_runtime_integration_decision import decide_runtime_integration
 d=decide_runtime_integration(c);w=wire_runtime_integration(d);return c,d,w
def test_complete_chain_verifies_with_bounded_evidence():
 c,d,w=chain();v=verify_runtime_integration(c,d,w);assert v["status"]=="verified" and all(v["evidence"].values()) and v["verification_payload"]==w["wiring_payload"]
def test_tampered_chain_is_invalid_not_repaired():
 c,d,w=chain();w["fingerprint"]="bad";assert verify_runtime_integration(c,d,w)["status"]=="invalid"
