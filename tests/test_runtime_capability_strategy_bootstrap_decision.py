from core.runtime.runtime_capability_strategy_runtime_decision import decide_capability_strategy_runtime
from core.runtime.runtime_capability_strategy_bootstrap_decision import decide_capability_strategy_bootstrap
from tests.capability_strategy_runtime_fixtures import strategy


def test_bootstrap_decision_records_accepted_fields_and_linkage():
    source = decide_capability_strategy_runtime(strategy(tools=("python",)))
    first = decide_capability_strategy_bootstrap(source); second = decide_capability_strategy_bootstrap(source)
    assert first == second and first["status"] == "accepted"
    assert "worker_limit" in first["accepted_configuration_fields"]
    assert first["source_runtime_decision_linkage"]["fingerprint"] == source["fingerprint"]
    assert first["source_strategy_linkage"] == source["strategy_linkage"]


def test_fallback_and_rejection_are_explicit():
    fallback = decide_capability_strategy_bootstrap(decide_capability_strategy_runtime(strategy("unknown_capability", workers=8)))
    assert fallback["status"] == "degraded" and fallback["fallback_applied"] is True
    assert fallback["fallback_reasons"] and fallback["downgraded_configuration_fields"]
    rejected = decide_capability_strategy_bootstrap({})
    assert rejected["status"] == "rejected" and rejected["configuration"] is None
    assert rejected["rejected_configuration_fields"] == ["configuration"]
    assert rejected["authority_granted"] is False and rejected["executor_ownership_changed"] is False
