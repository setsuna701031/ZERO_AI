from copy import deepcopy
import hashlib
import json

from core.runtime.runtime_capability_strategy_runtime_decision import decide_capability_strategy_runtime
from core.runtime.runtime_capability_strategy_bootstrap_configuration import configure_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_wiring import build_bootstrap_wiring_request, run_existing_bootstrap_builder, wire_capability_strategy_bootstrap
from tests.capability_strategy_runtime_fixtures import strategy


def _configuration(mode="cpu_only", **kwargs):
    return configure_capability_strategy_bootstrap(decide_capability_strategy_runtime(strategy(mode, **kwargs)))


def test_valid_stage_wiring_is_deterministic_linked_and_read_only():
    configuration = _configuration("accelerator_available", workers=4, compute="accelerator", tools=("python",))
    original = deepcopy(configuration)
    for stage in ("plan", "integration", "consumer"):
        request = build_bootstrap_wiring_request(bootstrap_configuration=configuration, target_bootstrap_stage=stage)
        first = wire_capability_strategy_bootstrap(request); second = wire_capability_strategy_bootstrap(request)
        assert first == second and first["status"] == "wired" and first["configuration_applied"] is True
        assert first["source_bootstrap_configuration_id"] == configuration["configuration_id"]
        assert first["source_runtime_decision_id"] == configuration["source_runtime_decision_linkage"]["decision_id"]
        assert first["source_strategy_id"] == configuration["source_strategy_linkage"]["strategy_id"]
        assert first["source_profile_id"] == configuration["source_strategy_linkage"]["profile_id"]
        assert first["runtime_started"] is False and first["authority_granted"] is False
        assert first["executor_ownership_changed"] is False
    assert configuration == original


def test_disabled_missing_default_and_rejected_configurations():
    configuration = _configuration()
    disabled = wire_capability_strategy_bootstrap(build_bootstrap_wiring_request(bootstrap_configuration=configuration, enabled=False))
    missing = wire_capability_strategy_bootstrap(build_bootstrap_wiring_request(bootstrap_configuration=None))
    default = configure_capability_strategy_bootstrap(decide_capability_strategy_runtime(None))
    compatible = wire_capability_strategy_bootstrap(build_bootstrap_wiring_request(bootstrap_configuration=default))
    rejected_config = configure_capability_strategy_bootstrap(decide_capability_strategy_runtime({}))
    rejected = wire_capability_strategy_bootstrap(build_bootstrap_wiring_request(bootstrap_configuration=rejected_config))
    assert disabled["status"] == "disabled" and disabled["effective_bootstrap_options"] is None
    assert missing["status"] == compatible["status"] == "default_compatible"
    assert missing["effective_bootstrap_options"] is compatible["effective_bootstrap_options"] is None
    assert rejected["status"] == "rejected" and rejected["configuration_applied"] is False


def test_ephemeral_runner_returns_only_existing_builder_identity():
    configuration = _configuration(workers=2)
    request = build_bootstrap_wiring_request(bootstrap_configuration=configuration, target_bootstrap_stage="plan")
    def existing_builder(*, payload, maximum_workers=8):
        base = {"schema": "existing.bootstrap.frozen.v1", "payload": payload, "maximum_workers": maximum_workers}
        fingerprint = hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()
        return {**base, "artifact_id": "existing-" + fingerprint[:24], "fingerprint": fingerprint}
    def translator(options, kwargs):
        return {**kwargs, "maximum_workers": min(kwargs["maximum_workers"], options["worker_limit"])}
    result = run_existing_bootstrap_builder(existing_builder, builder_kwargs={"payload": "unchanged", "maximum_workers": 8}, wiring_request=request, option_translator=translator)
    assert result["schema"] == "existing.bootstrap.frozen.v1" and result["maximum_workers"] == 2
    assert not any(key.startswith("wiring") or key.startswith("source_") for key in result)
    plain = run_existing_bootstrap_builder(existing_builder, builder_kwargs={"payload": "unchanged"})
    assert plain == existing_builder(payload="unchanged")
