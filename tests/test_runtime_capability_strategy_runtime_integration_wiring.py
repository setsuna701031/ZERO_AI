from copy import deepcopy
from core.runtime.runtime_capability_strategy_runtime_integration_decision import decide_runtime_integration
from core.runtime.runtime_capability_strategy_runtime_integration_wiring import wire_runtime_integration
from tests.test_runtime_capability_strategy_runtime_integration_decision import configuration
def decision():return decide_runtime_integration(configuration())
def test_wiring_is_passive_deterministic_and_payload_equal():
 d=decision();a=wire_runtime_integration(d);b=wire_runtime_integration(deepcopy(d));assert a==b and a["status"]=="wired" and a["wiring_payload"]==d["decision_payload"] and a["boundary"]["live_binding"] is False
def test_invalid_decision_is_not_promoted():
 d=decision();d["fingerprint"]="bad";out=wire_runtime_integration(d);assert out["status"]=="invalid" and out["wiring_payload"] is None
