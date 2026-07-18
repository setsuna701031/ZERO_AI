from copy import deepcopy

from core.runtime.runtime_capability_strategy_runtime_decision import decide_capability_strategy_runtime
from core.runtime.runtime_capability_strategy_bootstrap_configuration import configure_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_wiring import build_bootstrap_wiring_request, wire_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_consumption import consume_capability_strategy_bootstrap_wiring
from core.runtime.runtime_capability_strategy_bootstrap_runtime_integration_boundary import integrate_bootstrap_consumption
from core.runtime.runtime_capability_strategy_runtime_integration_consumer import consume_runtime_integration_boundary
from tests.capability_strategy_runtime_fixtures import strategy


def _boundary(**request_kwargs):
    configuration = configure_capability_strategy_bootstrap(decide_capability_strategy_runtime(strategy(workers=2, tools=("python",))))
    wiring = wire_capability_strategy_bootstrap(build_bootstrap_wiring_request(bootstrap_configuration=configuration, **request_kwargs))
    return integrate_bootstrap_consumption(consume_capability_strategy_bootstrap_wiring(wiring))


def test_consumer_is_deterministic_stable_linked_passive_and_read_only():
    boundary = _boundary(target_bootstrap_stage="integration"); original = deepcopy(boundary)
    first = consume_runtime_integration_boundary(boundary); second = consume_runtime_integration_boundary(boundary)
    assert first == second and first["status"] == "consumed"
    assert first["consumer_id"] == second["consumer_id"] and first["fingerprint"] == second["fingerprint"]
    assert first["source_integration_boundary_id"] == boundary["boundary_id"]
    assert first["source_integration_boundary_fingerprint"] == boundary["fingerprint"]
    for key in ("source_consumption_id", "source_wiring_id", "source_bootstrap_configuration_id", "source_runtime_decision_id", "source_strategy_id", "source_profile_id"):
        assert first[key] == boundary[key]
    assert first["consumer_payload"] == boundary["integration_payload"]
    assert first["boundary"]["runtime_activation"] is False and boundary == original


def test_default_rejected_and_invalid_fail_safe_without_payload():
    default = consume_runtime_integration_boundary(_boundary(enabled=False))
    rejected_configuration = configure_capability_strategy_bootstrap(decide_capability_strategy_runtime({}))
    rejected_wiring = wire_capability_strategy_bootstrap(build_bootstrap_wiring_request(bootstrap_configuration=rejected_configuration))
    rejected_boundary = integrate_bootstrap_consumption(consume_capability_strategy_bootstrap_wiring(rejected_wiring))
    rejected = consume_runtime_integration_boundary(rejected_boundary)
    invalid_boundary = deepcopy(_boundary()); invalid_boundary["fingerprint"] = "0" * 64
    invalid = consume_runtime_integration_boundary(invalid_boundary)
    assert default["status"] == "default_compatible" and default["consumer_payload"] is None
    assert rejected["status"] == "rejected" and rejected["consumer_payload"] is None
    assert invalid["status"] == "invalid" and invalid["consumer_payload"] is None


def test_import_has_no_side_effects():
    import core.runtime.runtime_capability_strategy_runtime_integration_consumer as module
    assert module.SCHEMA == "zero.runtime.capability_strategy_runtime_integration_consumer.v1"
