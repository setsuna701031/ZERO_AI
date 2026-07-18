from copy import deepcopy

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_runtime_decision import decide_capability_strategy_runtime
from core.runtime.runtime_capability_strategy_bootstrap_configuration import configure_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_wiring import build_bootstrap_wiring_request, wire_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_consumption import consume_capability_strategy_bootstrap_wiring
from core.runtime.runtime_capability_strategy_bootstrap_runtime_integration_boundary import integrate_bootstrap_consumption
from core.runtime.runtime_capability_strategy_bootstrap_runtime_integration_boundary_validation import validate_bootstrap_runtime_integration_boundary
from tests.capability_strategy_runtime_fixtures import strategy


def _artifacts():
    configuration = configure_capability_strategy_bootstrap(decide_capability_strategy_runtime(strategy(workers=2, tools=("python",))))
    wiring = wire_capability_strategy_bootstrap(build_bootstrap_wiring_request(bootstrap_configuration=configuration))
    consumption = consume_capability_strategy_bootstrap_wiring(wiring)
    return consumption, integrate_bootstrap_consumption(consumption)


def _reidentify(value):
    base = {key: item for key, item in value.items() if key not in {"boundary_id", "fingerprint"}}
    return _identified(base, "boundary_id", "capability-strategy-bootstrap-runtime-integration-boundary-")


def test_valid_boundary_and_top_level_or_nested_tampering():
    consumption, boundary = _artifacts()
    assert validate_bootstrap_runtime_integration_boundary(boundary, consumption).valid
    fingerprint = deepcopy(boundary); fingerprint["fingerprint"] = "0" * 64
    nested = deepcopy(boundary); nested["integration_payload"]["effective_bootstrap_options"]["worker_limit"] = 1; nested = _reidentify(nested)
    assert not validate_bootstrap_runtime_integration_boundary(fingerprint, consumption).valid
    assert "source_consumption_mismatch" in validate_bootstrap_runtime_integration_boundary(nested, consumption).errors


def test_unknown_missing_contradiction_linkage_and_scope_expansion_rejected():
    consumption, boundary = _artifacts()
    variants = []
    unknown = deepcopy(boundary); unknown["extra"] = True; variants.append(unknown)
    missing = deepcopy(boundary); del missing["source_consumption_id"]; variants.append(missing)
    contradiction = deepcopy(boundary); contradiction["status"] = "rejected"; variants.append(_reidentify(contradiction))
    linkage = deepcopy(boundary); linkage["source_profile_id"] = "other"; variants.append(_reidentify(linkage))
    expanded = deepcopy(boundary); expanded["integration_payload"]["effective_bootstrap_options"]["worker_limit"] = 99; variants.append(_reidentify(expanded))
    assert all(not validate_bootstrap_runtime_integration_boundary(item, consumption).valid for item in variants)


def test_active_domain_environment_path_command_and_callable_fields_rejected():
    consumption, boundary = _artifacts()
    keys = ("executor_target", "scheduler_queue", "planner_command", "mission_id", "agent_id", "approval_token", "authorization_token", "mutation_plan", "runtime_started", "environment_probe", "import_path", "shell_command", "callback")
    for key in keys:
        changed = deepcopy(boundary); changed["integration_payload"][key] = "C:\\machine\\command.exe"; changed = _reidentify(changed)
        assert not validate_bootstrap_runtime_integration_boundary(changed, consumption).valid
    callable_payload = deepcopy(boundary); callable_payload["integration_payload"]["callback"] = lambda: None
    assert not validate_bootstrap_runtime_integration_boundary(callable_payload, consumption).valid
    for unsafe_tool in ("C:\\machine\\tool.exe", "/usr/bin/tool", "tool; run", "tool | run"):
        changed = deepcopy(boundary); changed["integration_payload"]["effective_bootstrap_options"]["available_tools"] = [unsafe_tool]; changed = _reidentify(changed)
        assert not validate_bootstrap_runtime_integration_boundary(changed).valid


def test_builder_fails_safe_for_identity_valid_command_like_source_payload():
    consumption, _ = _artifacts()
    consumption["consumer_payload"]["effective_bootstrap_options"]["available_tools"] = ["C:\\machine\\tool.exe"]
    consumption = _identified({key: item for key, item in consumption.items() if key not in {"consumption_id", "fingerprint"}}, "consumption_id", "capability-strategy-bootstrap-consumption-")
    boundary = integrate_bootstrap_consumption(consumption)
    assert boundary["status"] == "invalid" and boundary["integration_payload"] is None
