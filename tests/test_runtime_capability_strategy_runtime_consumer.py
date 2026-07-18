from core.runtime.runtime_capability_strategy_runtime_consumer import consume_capability_strategy
from tests.capability_strategy_runtime_fixtures import strategy


def test_accelerator_and_cpu_strategies_are_deterministic_and_bounded():
    accelerator = strategy("accelerator_available", workers=6, compute="accelerator", tools=("zeta", "alpha"))
    first = consume_capability_strategy(accelerator); second = consume_capability_strategy(accelerator)
    assert first == second and first["status"] == "consumed"
    assert first["runtime_directives"]["accelerator_mode"] == "cuda"
    assert first["runtime_directives"]["available_tools"] == ["alpha", "zeta"]
    assert first["runtime_directives"]["worker_limit"] == 6
    cpu = consume_capability_strategy(strategy())
    assert cpu["runtime_directives"]["accelerator_mode"] == "disabled"


def test_resource_and_power_constraints_are_not_expanded():
    for value in (
        strategy("memory_constrained", workers=2, constraints=("memory_constrained",)),
        strategy("cpu_only", workers=2, constraints=("power_constrained",)),
    ):
        result = consume_capability_strategy(value)["runtime_directives"]
        assert result["worker_limit"] <= value["execution_preferences"]["parallelism"]["max_workers"]
        assert result["network_mode"] == "offline_safe" and result["accelerator_mode"] == "disabled"
        assert set(result["available_tools"]) <= {item["name"] for item in value["tool_preferences"]}


def test_unknown_capability_uses_safe_fallback_without_tool_expansion():
    value = strategy("unknown_capability", workers=7, compute="auto", tools=("declared",))
    result = consume_capability_strategy(value)
    directives = result["runtime_directives"]
    assert result["status"] == "fallback" and directives["fallback_applied"] is True
    assert directives["worker_limit"] == 1 and directives["execution_mode"] == "cpu_only"
    assert directives["network_mode"] == "offline_safe" and directives["accelerator_mode"] == "disabled"
    assert directives["available_tools"] == ["declared"]


def test_invalid_and_default_compatibility_fail_closed():
    assert consume_capability_strategy({"schema": "wrong"})["status"] == "invalid"
    assert consume_capability_strategy(None)["status"] == "default_compatible"
    assert consume_capability_strategy(strategy(), enabled=False)["status"] == "default_compatible"
