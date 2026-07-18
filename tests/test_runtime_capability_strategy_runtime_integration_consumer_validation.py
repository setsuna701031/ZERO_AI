from copy import deepcopy

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_runtime_decision import decide_capability_strategy_runtime
from core.runtime.runtime_capability_strategy_bootstrap_configuration import configure_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_wiring import build_bootstrap_wiring_request, wire_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_consumption import consume_capability_strategy_bootstrap_wiring
from core.runtime.runtime_capability_strategy_bootstrap_runtime_integration_boundary import integrate_bootstrap_consumption
from core.runtime.runtime_capability_strategy_runtime_integration_consumer import consume_runtime_integration_boundary
from core.runtime.runtime_capability_strategy_runtime_integration_consumer_validation import validate_runtime_integration_consumer
from tests.capability_strategy_runtime_fixtures import strategy


def _artifacts():
    configuration = configure_capability_strategy_bootstrap(decide_capability_strategy_runtime(strategy(workers=2, tools=("python",))))
    wiring = wire_capability_strategy_bootstrap(build_bootstrap_wiring_request(bootstrap_configuration=configuration))
    boundary = integrate_bootstrap_consumption(consume_capability_strategy_bootstrap_wiring(wiring))
    return boundary, consume_runtime_integration_boundary(boundary)


def _reidentify(value):
    base = {key: item for key, item in value.items() if key not in {"consumer_id", "fingerprint"}}
    return _identified(base, "consumer_id", "capability-strategy-runtime-integration-consumer-")


def test_valid_consumer_and_fingerprint_linkage_or_nested_tampering_rejected():
    boundary, consumer = _artifacts()
    assert validate_runtime_integration_consumer(consumer, boundary).valid
    fingerprint = deepcopy(consumer); fingerprint["fingerprint"] = "0" * 64
    linkage = deepcopy(consumer); linkage["source_integration_boundary_id"] = "other"; linkage = _reidentify(linkage)
    nested = deepcopy(consumer); nested["consumer_payload"]["effective_bootstrap_options"]["worker_limit"] = 1; nested = _reidentify(nested)
    assert not validate_runtime_integration_consumer(fingerprint, boundary).valid
    assert "source_boundary_mismatch" in validate_runtime_integration_consumer(linkage, boundary).errors
    assert "source_boundary_mismatch" in validate_runtime_integration_consumer(nested, boundary).errors


def test_unknown_missing_type_contradiction_and_scope_expansion_rejected():
    boundary, consumer = _artifacts(); variants = []
    unknown = deepcopy(consumer); unknown["extra"] = True; variants.append(unknown)
    missing = deepcopy(consumer); del missing["source_consumption_id"]; variants.append(missing)
    wrong_type = deepcopy(consumer); wrong_type["consumer_payload"]["effective_bootstrap_options"]["worker_limit"] = "2"; variants.append(_reidentify(wrong_type))
    contradiction = deepcopy(consumer); contradiction["status"] = "rejected"; variants.append(_reidentify(contradiction))
    expanded = deepcopy(consumer); expanded["consumer_payload"]["effective_bootstrap_options"]["worker_limit"] = 99; variants.append(_reidentify(expanded))
    assert all(not validate_runtime_integration_consumer(item, boundary).valid for item in variants)


def test_active_domains_paths_commands_environment_and_callable_rejected():
    boundary, consumer = _artifacts()
    keys = ("runtime_target", "executor_target", "scheduler_queue", "planner_command", "mission_id", "agent_id", "approval_record", "authorization_token", "mutation_plan", "callback", "handler", "adapter", "plugin", "import_path", "shell_command", "activation_flag", "environment_probe")
    for key in keys:
        changed = deepcopy(consumer); changed["consumer_payload"][key] = "C:\\machine\\command.exe"; changed = _reidentify(changed)
        assert not validate_runtime_integration_consumer(changed, boundary).valid
    for unsafe_tool in ("C:\\machine\\tool.exe", "/usr/bin/tool", "tool; run", "tool | run"):
        changed = deepcopy(consumer); changed["consumer_payload"]["effective_bootstrap_options"]["available_tools"] = [unsafe_tool]; changed = _reidentify(changed)
        assert not validate_runtime_integration_consumer(changed).valid
    callable_value = deepcopy(consumer); callable_value["consumer_payload"]["callback"] = lambda: None
    assert not validate_runtime_integration_consumer(callable_value).valid
