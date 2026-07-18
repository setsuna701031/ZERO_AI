from copy import deepcopy

from core.runtime.runtime_capability_strategy_runtime_decision import decide_capability_strategy_runtime
from core.runtime.runtime_capability_strategy_bootstrap_configuration import configure_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_wiring import build_bootstrap_wiring_request, wire_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_consumption import consume_capability_strategy_bootstrap_wiring
from tests.capability_strategy_runtime_fixtures import strategy


def _wiring(**request_kwargs):
    configuration = configure_capability_strategy_bootstrap(decide_capability_strategy_runtime(strategy(workers=2, tools=("python",))))
    return wire_capability_strategy_bootstrap(build_bootstrap_wiring_request(bootstrap_configuration=configuration, **request_kwargs))


def test_consumption_is_deterministic_stable_linked_and_read_only():
    wiring = _wiring(target_bootstrap_stage="consumer")
    original = deepcopy(wiring)
    first = consume_capability_strategy_bootstrap_wiring(wiring)
    second = consume_capability_strategy_bootstrap_wiring(wiring)
    assert first == second
    assert first["status"] == "consumed"
    assert first["consumption_id"] == second["consumption_id"]
    assert first["fingerprint"] == second["fingerprint"]
    assert first["source_wiring_id"] == wiring["wiring_id"]
    assert first["source_wiring_fingerprint"] == wiring["fingerprint"]
    assert first["source_strategy_id"] == wiring["source_strategy_id"]
    assert first["source_profile_id"] == wiring["source_profile_id"]
    assert first["consumer_payload"]["effective_bootstrap_options"] == wiring["effective_bootstrap_options"]
    assert wiring == original


def test_non_consumable_rejected_and_invalid_wiring_fail_safe():
    disabled = _wiring(enabled=False)
    rejected_configuration = configure_capability_strategy_bootstrap(decide_capability_strategy_runtime({}))
    rejected = wire_capability_strategy_bootstrap(build_bootstrap_wiring_request(bootstrap_configuration=rejected_configuration))
    invalid = deepcopy(_wiring()); invalid["fingerprint"] = "0" * 64
    assert consume_capability_strategy_bootstrap_wiring(disabled)["status"] == "default_compatible"
    blocked = consume_capability_strategy_bootstrap_wiring(rejected)
    assert blocked["status"] == "rejected" and blocked["consumer_payload"] is None
    failed = consume_capability_strategy_bootstrap_wiring(invalid)
    assert failed["status"] == "invalid" and failed["consumer_payload"] is None


def test_import_has_no_runtime_side_effects():
    import core.runtime.runtime_capability_strategy_bootstrap_consumption as module
    assert module.SCHEMA == "zero.runtime.capability_strategy_bootstrap_consumption.v1"
