from copy import deepcopy

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_runtime_decision import decide_capability_strategy_runtime
from core.runtime.runtime_capability_strategy_bootstrap_configuration import configure_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_wiring import build_bootstrap_wiring_request, wire_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_consumption import consume_capability_strategy_bootstrap_wiring
from core.runtime.runtime_capability_strategy_bootstrap_runtime_integration_boundary import integrate_bootstrap_consumption
from core.runtime.runtime_capability_strategy_runtime_integration_consumer import consume_runtime_integration_boundary
from core.runtime.runtime_capability_strategy_runtime_integration_configuration import configure_runtime_integration
from core.runtime.runtime_capability_strategy_runtime_integration_configuration_validation import validate_runtime_integration_configuration
from tests.capability_strategy_runtime_fixtures import strategy


def _artifacts():
    bootstrap = configure_capability_strategy_bootstrap(decide_capability_strategy_runtime(strategy(workers=2, tools=("python",))))
    wiring = wire_capability_strategy_bootstrap(build_bootstrap_wiring_request(bootstrap_configuration=bootstrap))
    boundary = integrate_bootstrap_consumption(consume_capability_strategy_bootstrap_wiring(wiring))
    consumer = consume_runtime_integration_boundary(boundary)
    return consumer, configure_runtime_integration(consumer)


def _reidentify(value):
    base = {key: item for key, item in value.items() if key not in {"configuration_id", "fingerprint"}}
    return _identified(base, "configuration_id", "capability-strategy-runtime-integration-configuration-")


def test_valid_and_tampered_fingerprint_linkage_or_payload_rejected():
    consumer, configuration = _artifacts()
    assert validate_runtime_integration_configuration(configuration, consumer).valid
    fingerprint = deepcopy(configuration); fingerprint["fingerprint"] = "0" * 64
    linkage = deepcopy(configuration); linkage["source_integration_consumer_id"] = "other"; linkage = _reidentify(linkage)
    nested = deepcopy(configuration); nested["configuration_payload"]["effective_bootstrap_options"]["worker_limit"] = 1; nested = _reidentify(nested)
    assert not validate_runtime_integration_configuration(fingerprint, consumer).valid
    assert "source_consumer_mismatch" in validate_runtime_integration_configuration(linkage, consumer).errors
    assert "source_consumer_mismatch" in validate_runtime_integration_configuration(nested, consumer).errors


def test_unknown_missing_type_empty_identity_contradiction_and_weakening_rejected():
    consumer, configuration = _artifacts(); variants = []
    unknown = deepcopy(configuration); unknown["extra"] = True; variants.append(unknown)
    missing = deepcopy(configuration); del missing["source_consumption_id"]; variants.append(missing)
    wrong_type = deepcopy(configuration); wrong_type["configuration_payload"]["effective_bootstrap_options"]["worker_limit"] = "2"; variants.append(_reidentify(wrong_type))
    empty = deepcopy(configuration); empty["configuration_id"] = " "; variants.append(empty)
    contradiction = deepcopy(configuration); contradiction["status"] = "rejected"; variants.append(_reidentify(contradiction))
    weakened = deepcopy(configuration); weakened["configuration_payload"]["effective_bootstrap_options"]["worker_limit"] = 99; variants.append(_reidentify(weakened))
    expanded = deepcopy(configuration); expanded["configuration_payload"]["new_scope"] = True; variants.append(_reidentify(expanded))
    assert all(not validate_runtime_integration_configuration(item, consumer).valid for item in variants)


def test_active_domains_non_json_paths_commands_and_environment_rejected():
    consumer, configuration = _artifacts()
    keys = ("runtime_component", "executor_target", "scheduler_queue", "planner_command", "mission_id", "agent_id", "approval_record", "authorization_token", "mutation_plan", "callback", "handler", "adapter", "provider", "plugin", "import_path", "shell_command", "activation_flag", "environment_probe")
    for key in keys:
        changed = deepcopy(configuration); changed["configuration_payload"][key] = "C:\\machine\\command.exe"; changed = _reidentify(changed)
        assert not validate_runtime_integration_configuration(changed, consumer).valid
    for unsafe_tool in ("C:\\machine\\tool.exe", "/usr/bin/tool", "tool; run", "tool | run"):
        changed = deepcopy(configuration); changed["configuration_payload"]["effective_bootstrap_options"]["available_tools"] = [unsafe_tool]; changed = _reidentify(changed)
        assert not validate_runtime_integration_configuration(changed).valid
    callable_value = deepcopy(configuration); callable_value["configuration_payload"]["callback"] = lambda: None
    live_object = deepcopy(configuration); live_object["configuration_payload"]["object"] = object()
    assert not validate_runtime_integration_configuration(callable_value).valid
    assert not validate_runtime_integration_configuration(live_object).valid
