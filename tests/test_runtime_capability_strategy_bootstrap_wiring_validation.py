from copy import deepcopy

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_runtime_decision import decide_capability_strategy_runtime
from core.runtime.runtime_capability_strategy_bootstrap_configuration import configure_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_wiring import build_bootstrap_wiring_request, wire_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_wiring_validation import validate_wiring_request, validate_wiring_result
from tests.capability_strategy_runtime_fixtures import strategy


def _configuration(): return configure_capability_strategy_bootstrap(decide_capability_strategy_runtime(strategy(workers=2, tools=("python",))))


def test_request_and_result_validation_identity_and_targets():
    configuration = _configuration()
    for stage in ("plan", "integration", "consumer"):
        request = build_bootstrap_wiring_request(bootstrap_configuration=configuration, target_bootstrap_stage=stage)
        result = wire_capability_strategy_bootstrap(request)
        assert validate_wiring_request(request).valid
        assert validate_wiring_result(result, configuration).valid
    request = build_bootstrap_wiring_request(bootstrap_configuration=configuration)
    for key in ("schema", "fingerprint", "enabled"):
        changed = deepcopy(request)
        if key == "schema": changed[key] = "invalid"
        elif key == "fingerprint": changed[key] = "0" * 64
        else: del changed[key]
        assert not validate_wiring_request(changed).valid
        assert wire_capability_strategy_bootstrap(changed)["status"] == "invalid"
    unsupported = build_bootstrap_wiring_request(bootstrap_configuration=configuration, target_bootstrap_stage="executor")
    assert wire_capability_strategy_bootstrap(unsupported)["status"] == "invalid"


def test_monotonic_restrictions_reject_expanded_effective_options():
    configuration = _configuration()
    result = wire_capability_strategy_bootstrap(build_bootstrap_wiring_request(bootstrap_configuration=configuration))
    for key, value in (("worker_limit", 3), ("available_tools", ["python", "shell"]), ("network_mode", "unrestricted"), ("accelerator_mode", "cuda"), ("execution_mode", "accelerator_available"), ("resource_mode", "unbounded")):
        changed = deepcopy(result); changed["effective_bootstrap_options"][key] = value
        changed = _identified({k: v for k, v in changed.items() if k not in {"wiring_id", "fingerprint"}}, "wiring_id", "capability-strategy-bootstrap-wiring-")
        validation = validate_wiring_result(changed, configuration)
        assert not validation.valid and "monotonic_restriction_violation" in validation.errors


def test_frozen_bootstrap_schema_constants_remain_unchanged():
    from core.runtime.runtime_capability_bootstrap_plan import SCHEMA as PLAN
    from core.runtime.runtime_capability_bootstrap_integration import INTEGRATION_SCHEMA as INTEGRATION
    from core.runtime.runtime_capability_bootstrap_consumer import RESULT_SCHEMA as CONSUMER
    assert PLAN == "zero.runtime.capability_bootstrap_plan.v1"
    assert INTEGRATION == "zero.runtime.capability_bootstrap_integration.v1"
    assert CONSUMER == "zero.runtime.capability_bootstrap_consumption_result.v1"
