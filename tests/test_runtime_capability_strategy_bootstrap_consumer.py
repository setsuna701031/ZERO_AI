from core.runtime.runtime_capability_strategy_runtime_decision import decide_capability_strategy_runtime
from core.runtime.runtime_capability_strategy_bootstrap_consumer import consume_runtime_strategy_decision
from tests.capability_strategy_runtime_fixtures import strategy


def _decision(mode="cpu_only", **kwargs): return decide_capability_strategy_runtime(strategy(mode, **kwargs))


def test_accepted_accelerator_and_cpu_decisions_are_deterministic():
    for source in (_decision("accelerator_available", workers=6, compute="accelerator", tools=("zeta", "alpha")), _decision()):
        first = consume_runtime_strategy_decision(source); second = consume_runtime_strategy_decision(source)
        assert first == second and first["status"] == "consumed"
        fields = first["configuration_fields"]
        assert fields["worker_limit"] <= source["accepted_directives"]["worker_limit"]
        assert set(fields["available_tools"]) <= set(source["accepted_directives"]["available_tools"])
        assert fields["source_runtime_decision_id"] == source["decision_id"]
        assert fields["source_strategy_id"] == source["strategy_linkage"]["strategy_id"]


def test_degraded_resource_and_power_restrictions_are_monotonic():
    unknown = _decision("unknown_capability", workers=8, compute="auto", tools=("declared",))
    result = consume_runtime_strategy_decision(unknown)
    fields = result["configuration_fields"]
    assert result["status"] == "fallback" and fields["worker_limit"] == 1
    assert fields["execution_mode"] == "cpu_only" and fields["network_mode"] == "offline_safe"
    assert fields["accelerator_mode"] == "disabled" and fields["available_tools"] == ["declared"]
    for source in (_decision("memory_constrained", workers=2), _decision("cpu_only", workers=2, constraints=("power_constrained",))):
        fields = consume_runtime_strategy_decision(source)["configuration_fields"]
        assert fields["worker_limit"] <= source["accepted_directives"]["worker_limit"]
        assert fields["network_mode"] == source["accepted_directives"]["network_mode"]


def test_default_compatible_does_not_invent_configuration():
    source = decide_capability_strategy_runtime(None)
    result = consume_runtime_strategy_decision(source); fields = result["configuration_fields"]
    assert result["status"] == "default_compatible" and fields["compatibility_mode"] is True
    assert fields["available_tools"] == []
    assert all(fields[key] is None for key in ("worker_limit", "execution_mode", "network_mode", "resource_mode", "accelerator_mode"))


def test_rejected_or_invalid_decision_has_no_configuration():
    rejected = consume_runtime_strategy_decision(decide_capability_strategy_runtime({}))
    invalid = consume_runtime_strategy_decision({"schema": "wrong"})
    assert rejected["status"] == invalid["status"] == "rejected"
    assert rejected["configuration_fields"] is invalid["configuration_fields"] is None
