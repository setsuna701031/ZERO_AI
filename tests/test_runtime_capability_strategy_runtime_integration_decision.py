from copy import deepcopy
from core.runtime.runtime_capability_strategy_runtime_decision import decide_capability_strategy_runtime
from core.runtime.runtime_capability_strategy_bootstrap_configuration import configure_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_wiring import build_bootstrap_wiring_request, wire_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_consumption import consume_capability_strategy_bootstrap_wiring
from core.runtime.runtime_capability_strategy_bootstrap_runtime_integration_boundary import integrate_bootstrap_consumption
from core.runtime.runtime_capability_strategy_runtime_integration_consumer import consume_runtime_integration_boundary
from core.runtime.runtime_capability_strategy_runtime_integration_configuration import configure_runtime_integration
from core.runtime.runtime_capability_strategy_runtime_integration_decision import decide_runtime_integration
from tests.capability_strategy_runtime_fixtures import strategy

def configuration():
    b=configure_capability_strategy_bootstrap(decide_capability_strategy_runtime(strategy()))
    w=wire_capability_strategy_bootstrap(build_bootstrap_wiring_request(bootstrap_configuration=b))
    return configure_runtime_integration(consume_runtime_integration_boundary(integrate_bootstrap_consumption(consume_capability_strategy_bootstrap_wiring(w))))

def test_decision_is_deterministic_stable_and_payload_equal():
    source=configuration(); a=decide_runtime_integration(source); b=decide_runtime_integration(deepcopy(source))
    assert a==b and a["status"]=="decided" and a["decision_payload"]==source["configuration_payload"]
    assert a["decision_id"].endswith(a["fingerprint"][:24]) and a["boundary"]["authority_granted"] is False

def test_decision_fail_safe_statuses():
    source=configuration()
    for before,after in (("default_compatible","default_compatible"),("rejected","rejected"),("invalid","invalid")):
        changed=deepcopy(source);changed["status"]=before;changed["configuration_payload"]=None
        from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
        changed=_identified({k:v for k,v in changed.items() if k not in {"configuration_id","fingerprint"}},"configuration_id","capability-strategy-runtime-integration-configuration-")
        out=decide_runtime_integration(changed);assert out["status"]==after and out["decision_payload"] is None
