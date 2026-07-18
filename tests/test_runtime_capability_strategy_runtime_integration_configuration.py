from copy import deepcopy

from core.runtime.runtime_capability_strategy_runtime_decision import decide_capability_strategy_runtime
from core.runtime.runtime_capability_strategy_bootstrap_configuration import configure_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_wiring import build_bootstrap_wiring_request, wire_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_consumption import consume_capability_strategy_bootstrap_wiring
from core.runtime.runtime_capability_strategy_bootstrap_runtime_integration_boundary import integrate_bootstrap_consumption
from core.runtime.runtime_capability_strategy_runtime_integration_consumer import consume_runtime_integration_boundary
from core.runtime.runtime_capability_strategy_runtime_integration_configuration import configure_runtime_integration
from tests.capability_strategy_runtime_fixtures import strategy


def _consumer(**request_kwargs):
    bootstrap = configure_capability_strategy_bootstrap(decide_capability_strategy_runtime(strategy(workers=2, tools=("python",))))
    wiring = wire_capability_strategy_bootstrap(build_bootstrap_wiring_request(bootstrap_configuration=bootstrap, **request_kwargs))
    boundary = integrate_bootstrap_consumption(consume_capability_strategy_bootstrap_wiring(wiring))
    return consume_runtime_integration_boundary(boundary)


def test_configuration_is_deterministic_stable_linked_and_monotonic():
    consumer = _consumer(target_bootstrap_stage="integration"); original = deepcopy(consumer)
    first = configure_runtime_integration(consumer); second = configure_runtime_integration(consumer)
    assert first == second and first["status"] == "configured"
    assert first["configuration_id"] == second["configuration_id"] and first["fingerprint"] == second["fingerprint"]
    assert first["source_integration_consumer_id"] == consumer["consumer_id"]
    assert first["source_integration_consumer_fingerprint"] == consumer["fingerprint"]
    for key in ("source_integration_boundary_id", "source_consumption_id", "source_wiring_id", "source_bootstrap_configuration_id", "source_runtime_decision_id", "source_strategy_id", "source_profile_id"):
        assert first[key] == consumer[key]
    assert first["configuration_payload"] == consumer["consumer_payload"]
    assert first["boundary"]["runtime_activation"] is False and consumer == original


def test_default_rejected_and_invalid_are_not_promoted():
    default = configure_runtime_integration(_consumer(enabled=False))
    rejected_bootstrap = configure_capability_strategy_bootstrap(decide_capability_strategy_runtime({}))
    rejected_wiring = wire_capability_strategy_bootstrap(build_bootstrap_wiring_request(bootstrap_configuration=rejected_bootstrap))
    rejected_boundary = integrate_bootstrap_consumption(consume_capability_strategy_bootstrap_wiring(rejected_wiring))
    rejected = configure_runtime_integration(consume_runtime_integration_boundary(rejected_boundary))
    invalid_consumer = deepcopy(_consumer()); invalid_consumer["fingerprint"] = "0" * 64
    invalid = configure_runtime_integration(invalid_consumer)
    assert default["status"] == "default_compatible" and default["configuration_payload"] is None
    assert rejected["status"] == "rejected" and rejected["configuration_payload"] is None
    assert invalid["status"] == "invalid" and invalid["configuration_payload"] is None


def test_import_has_no_side_effects():
    import core.runtime.runtime_capability_strategy_runtime_integration_configuration as module
    assert module.SCHEMA == "zero.runtime.capability_strategy_runtime_integration_configuration.v1"
