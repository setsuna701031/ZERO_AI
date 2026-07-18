from core.runtime.runtime_capability_strategy_runtime_decision import decide_capability_strategy_runtime
from tests.capability_strategy_runtime_fixtures import strategy


def test_decision_identity_linkage_acceptance_and_rejection():
    value = strategy(tools=("only-declared",))
    first = decide_capability_strategy_runtime(value); second = decide_capability_strategy_runtime(value)
    assert first == second and first["status"] == "accepted"
    assert first["strategy_linkage"]["strategy_id"] == value["strategy_id"]
    assert first["profile_linkage"]["profile_id"] == value["profile_id"]
    assert first["accepted_directives"]["available_tools"] == ["only-declared"]
    rejected = decide_capability_strategy_runtime({})
    assert rejected["status"] == "rejected" and rejected["rejected_directives"] == ["strategy_input"]


def test_decision_records_unknown_fallback_and_no_authority():
    result = decide_capability_strategy_runtime(strategy("unknown_capability", workers=8))
    assert result["status"] == "degraded" and result["fallback_applied"] is True
    assert result["fallback_reason"] == "unknown_capability" and result["degraded_directives"]
    assert result["authority_granted"] is False and result["decision_input_only"] is True
