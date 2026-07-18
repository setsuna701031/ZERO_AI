from core.runtime.runtime_capability_strategy_runtime_consumer import consume_capability_strategy
from core.runtime.runtime_capability_strategy_runtime_integration import integrate_capability_strategy_runtime
from tests.capability_strategy_runtime_fixtures import strategy


def test_integration_is_deterministic_and_preserves_linkage():
    value = strategy("storage_constrained", workers=1)
    consumer = consume_capability_strategy(value)
    first = integrate_capability_strategy_runtime(value); second = integrate_capability_strategy_runtime(value)
    assert first == second and first["status"] == "integrated"
    assert first["consumer_result_linkage"] == {"consumer_id": consumer["consumer_id"], "fingerprint": consumer["fingerprint"]}
    assert first["source_strategy_linkage"]["strategy_id"] == value["strategy_id"]
    assert first["runtime_directives"]["source_strategy_fingerprint"] == value["fingerprint"]


def test_integration_is_read_only_decision_input_and_invalid_is_explicit():
    result = integrate_capability_strategy_runtime({})
    assert result["status"] == "invalid" and result["runtime_directives"] is None
    assert result["decision_input_only"] is True and result["executor_ownership_changed"] is False
