from copy import deepcopy

from core.runtime.runtime_capability_strategy_runtime_decision import decide_capability_strategy_runtime
from core.runtime.runtime_capability_strategy_bootstrap_configuration import configure_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_wiring import build_bootstrap_wiring_request, wire_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_consumption import consume_capability_strategy_bootstrap_wiring
from core.runtime.runtime_capability_strategy_bootstrap_runtime_integration_boundary import integrate_bootstrap_consumption
from tests.capability_strategy_runtime_fixtures import strategy


def _consumption(**request_kwargs):
    configuration = configure_capability_strategy_bootstrap(decide_capability_strategy_runtime(strategy(workers=2, tools=("python",))))
    wiring = wire_capability_strategy_bootstrap(build_bootstrap_wiring_request(bootstrap_configuration=configuration, **request_kwargs))
    return consume_capability_strategy_bootstrap_wiring(wiring)


def test_boundary_is_deterministic_stable_linked_passive_and_read_only():
    consumption = _consumption(target_bootstrap_stage="integration")
    original = deepcopy(consumption)
    first = integrate_bootstrap_consumption(consumption); second = integrate_bootstrap_consumption(consumption)
    assert first == second and first["status"] == "integrated"
    assert first["boundary_id"] == second["boundary_id"] and first["fingerprint"] == second["fingerprint"]
    assert first["source_consumption_id"] == consumption["consumption_id"]
    assert first["source_consumption_fingerprint"] == consumption["fingerprint"]
    for key in ("source_wiring_id", "source_bootstrap_configuration_id", "source_runtime_decision_id", "source_strategy_id", "source_profile_id"):
        assert first[key] == consumption[key]
    assert first["integration_payload"] == consumption["consumer_payload"]
    assert first["boundary"]["runtime_activation"] is False
    assert consumption == original


def test_default_rejected_and_invalid_are_fail_safe_without_payload():
    default = integrate_bootstrap_consumption(_consumption(enabled=False))
    rejected_configuration = configure_capability_strategy_bootstrap(decide_capability_strategy_runtime({}))
    rejected_wiring = wire_capability_strategy_bootstrap(build_bootstrap_wiring_request(bootstrap_configuration=rejected_configuration))
    rejected = integrate_bootstrap_consumption(consume_capability_strategy_bootstrap_wiring(rejected_wiring))
    invalid_consumption = deepcopy(_consumption()); invalid_consumption["fingerprint"] = "0" * 64
    invalid = integrate_bootstrap_consumption(invalid_consumption)
    assert default["status"] == "default_compatible" and default["integration_payload"] is None
    assert rejected["status"] == "rejected" and rejected["integration_payload"] is None
    assert invalid["status"] == "invalid" and invalid["integration_payload"] is None


def test_import_has_no_side_effects():
    import core.runtime.runtime_capability_strategy_bootstrap_runtime_integration_boundary as module
    assert module.SCHEMA == "zero.runtime.capability_strategy_bootstrap_runtime_integration_boundary.v1"
