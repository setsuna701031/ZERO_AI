from core.runtime.runtime_policy_evolution import (
    ACTION_BLOCK_TOOL,
    ACTION_DISABLE_MUTATION,
    ACTION_LOWER_AUTONOMY,
    ACTION_REQUIRE_REVIEW,
    POLICY_MODE_NORMAL,
    POLICY_MODE_RESTRICTED,
    POLICY_MODE_REVIEW_REQUIRED,
    POLICY_MODE_SAFE,
    RuntimePolicyEvolution,
)


def test_policy_evolution_handles_review_required_patterns():
    runtime = RuntimePolicyEvolution()

    decision = runtime.evolve(
        stability_patterns=[
            {
                "pattern_key": "timeout",
                "count": 2,
                "affected_component": "tool_runner",
                "recommended_action": ACTION_REQUIRE_REVIEW,
            }
        ]
    )

    payload = decision.to_dict()

    assert payload["verified"] is True
    assert payload["policy_mode"] == POLICY_MODE_REVIEW_REQUIRED
    assert ACTION_REQUIRE_REVIEW in payload["applied_actions"]


def test_policy_evolution_handles_disable_mutation_patterns():
    runtime = RuntimePolicyEvolution()

    decision = runtime.evolve(
        stability_patterns=[
            {
                "pattern_key": "corruption",
                "count": 3,
                "affected_component": "mutation_engine",
                "recommended_action": ACTION_DISABLE_MUTATION,
            }
        ]
    )

    assert decision.policy_mode == POLICY_MODE_SAFE
    assert ACTION_DISABLE_MUTATION in decision.applied_actions


def test_policy_evolution_handles_block_tool_patterns():
    runtime = RuntimePolicyEvolution()

    decision = runtime.evolve(
        stability_patterns=[
            {
                "pattern_key": "unsafe_output",
                "count": 5,
                "affected_component": "shell_tool",
                "recommended_action": ACTION_BLOCK_TOOL,
            }
        ]
    )

    assert decision.policy_mode == POLICY_MODE_RESTRICTED
    assert ACTION_BLOCK_TOOL in decision.applied_actions
    assert ACTION_LOWER_AUTONOMY in decision.applied_actions
    assert decision.autonomy_level < 50


def test_policy_evolution_preserves_multiple_rules():
    runtime = RuntimePolicyEvolution()

    decision = runtime.evolve(
        stability_patterns=[
            {
                "pattern_key": "timeout",
                "count": 2,
                "affected_component": "tool_runner",
                "recommended_action": ACTION_REQUIRE_REVIEW,
            },
            {
                "pattern_key": "corruption",
                "count": 3,
                "affected_component": "mutation_engine",
                "recommended_action": ACTION_DISABLE_MUTATION,
            },
        ]
    )

    assert len(decision.generated_rules) >= 2


def test_policy_evolution_empty_patterns_remains_normal():
    runtime = RuntimePolicyEvolution()

    decision = runtime.evolve(stability_patterns=[])

    assert decision.policy_mode == POLICY_MODE_NORMAL
    assert decision.autonomy_level == 100
