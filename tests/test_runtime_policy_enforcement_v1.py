from core.runtime.runtime_policy_enforcement import (
    ACTION_BLOCK_TOOL,
    ACTION_DISABLE_MUTATION,
    ACTION_REQUIRE_REVIEW,
    EXECUTION_ALLOWED,
    EXECUTION_BLOCKED,
    EXECUTION_REVIEW_REQUIRED,
    EXECUTION_SAFE_MODE,
    POLICY_MODE_NORMAL,
    POLICY_MODE_REVIEW_REQUIRED,
    POLICY_MODE_SAFE,
    enforce_runtime_policy,
)


def test_policy_enforcement_allows_normal_execution():
    result = enforce_runtime_policy(
        step={
            "type": "tool",
            "tool": "safe_tool",
        },
        policy_mode=POLICY_MODE_NORMAL,
        applied_actions=[],
        autonomy_level=100,
    )

    payload = result.to_dict()

    assert payload["verified"] is True
    assert payload["execution_status"] == EXECUTION_ALLOWED
    assert payload["allowed"] is True


def test_policy_enforcement_blocks_unsafe_tool():
    result = enforce_runtime_policy(
        step={
            "type": "tool",
            "tool": "shell_tool",
        },
        policy_mode=POLICY_MODE_REVIEW_REQUIRED,
        applied_actions=[ACTION_BLOCK_TOOL],
        autonomy_level=40,
    )

    assert result.execution_status == EXECUTION_BLOCKED
    assert result.allowed is False
    assert result.reason == "tool_blocked_by_runtime_policy"


def test_policy_enforcement_blocks_mutation_path():
    result = enforce_runtime_policy(
        step={
            "type": "mutation",
        },
        policy_mode=POLICY_MODE_SAFE,
        applied_actions=[ACTION_DISABLE_MUTATION],
        autonomy_level=50,
    )

    assert result.execution_status == EXECUTION_BLOCKED
    assert result.reason == "mutation_path_disabled"


def test_policy_enforcement_requires_review_under_low_autonomy():
    result = enforce_runtime_policy(
        step={
            "type": "tool",
            "tool": "safe_tool",
        },
        policy_mode=POLICY_MODE_REVIEW_REQUIRED,
        applied_actions=[ACTION_REQUIRE_REVIEW],
        autonomy_level=60,
    )

    assert result.execution_status == EXECUTION_REVIEW_REQUIRED
    assert result.allowed is False


def test_policy_enforcement_safe_mode_allows_limited_execution():
    result = enforce_runtime_policy(
        step={
            "type": "tool",
            "tool": "safe_tool",
        },
        policy_mode=POLICY_MODE_SAFE,
        applied_actions=[],
        autonomy_level=80,
    )

    assert result.execution_status == EXECUTION_SAFE_MODE
    assert result.allowed is True
