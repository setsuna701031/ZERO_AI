from core.runtime.runtime_capability_strategy_runtime_decision import decide_capability_strategy_runtime
from core.runtime.runtime_capability_strategy_bootstrap_consumer import consume_runtime_strategy_decision
from core.runtime.runtime_capability_strategy_bootstrap_configuration import configure_capability_strategy_bootstrap
from tests.capability_strategy_runtime_fixtures import strategy


def test_configuration_is_deterministic_and_linked():
    source = decide_capability_strategy_runtime(strategy("accelerator_available", workers=4, compute="accelerator"))
    consumer = consume_runtime_strategy_decision(source)
    first = configure_capability_strategy_bootstrap(source); second = configure_capability_strategy_bootstrap(source)
    assert first == second and first["status"] == "configured"
    assert first["consumer_linkage"] == {"consumer_id": consumer["consumer_id"], "fingerprint": consumer["fingerprint"]}
    assert first["source_runtime_decision_linkage"]["decision_id"] == source["decision_id"]
    assert first["configuration"]["accelerator_mode"] == source["accepted_directives"]["accelerator_mode"]


def test_rejected_configuration_is_non_executable_and_has_no_authority():
    result = configure_capability_strategy_bootstrap({})
    assert result["status"] == "rejected" and result["configuration"] is None
    assert result["decision_input_only"] is True and result["authority_granted"] is False
    assert result["executor_ownership_changed"] is False
