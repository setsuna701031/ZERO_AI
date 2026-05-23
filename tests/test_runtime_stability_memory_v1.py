from core.runtime.runtime_stability_memory import (
    POLICY_ACTION_BLOCK_TOOL,
    POLICY_ACTION_DISABLE_MUTATION,
    POLICY_ACTION_REQUIRE_REVIEW,
    RuntimeStabilityMemory,
)


def test_stability_memory_detects_review_pattern():
    memory = RuntimeStabilityMemory()

    memory.remember(component="tool_runner", failure_type="timeout")
    memory.remember(component="tool_runner", failure_type="timeout")

    decision = memory.evaluate()
    payload = decision.to_dict()

    assert payload["verified"] is True
    assert payload["policy_action"] == POLICY_ACTION_REQUIRE_REVIEW
    assert payload["status"] == "degraded"


def test_stability_memory_detects_disable_mutation_pattern():
    memory = RuntimeStabilityMemory()

    for _ in range(3):
        memory.remember(component="mutation_engine", failure_type="corruption")

    decision = memory.evaluate()

    assert decision.policy_action == POLICY_ACTION_DISABLE_MUTATION
    assert decision.status == "degraded"


def test_stability_memory_detects_block_tool_pattern():
    memory = RuntimeStabilityMemory()

    for _ in range(5):
        memory.remember(component="shell_tool", failure_type="unsafe_output")

    decision = memory.evaluate()

    assert decision.policy_action == POLICY_ACTION_BLOCK_TOOL
    assert decision.status == "unstable"
    assert decision.health_score == 50


def test_stability_memory_preserves_multiple_patterns():
    memory = RuntimeStabilityMemory()

    memory.remember(component="tool_runner", failure_type="timeout")
    memory.remember(component="tool_runner", failure_type="timeout")
    memory.remember(component="mutation_engine", failure_type="corruption")

    decision = memory.evaluate()

    assert len(decision.detected_patterns) >= 2


def test_stability_memory_health_score_degrades():
    memory = RuntimeStabilityMemory()

    for _ in range(3):
        memory.remember(component="mutation_engine", failure_type="corruption")

    decision = memory.evaluate()

    assert decision.health_score < 100


def test_stability_memory_empty_history_is_healthy():
    memory = RuntimeStabilityMemory()

    decision = memory.evaluate()

    assert decision.status == "healthy"
    assert decision.policy_action == "none"
    assert decision.health_score == 100
