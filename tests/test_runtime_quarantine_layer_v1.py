from core.runtime.runtime_quarantine_layer import (
    ACTION_QUARANTINE,
    ACTION_REQUIRE_APPROVAL,
    ACTION_SANDBOX_ONLY,
    QUARANTINE_STATUS_ACTIVE,
    QUARANTINE_STATUS_RELEASED,
    TARGET_BRANCH,
    TARGET_MUTATION,
    TARGET_TOOL,
    RuntimeQuarantineLayer,
)


def test_quarantine_layer_blocks_critical_tool():
    runtime = RuntimeQuarantineLayer()

    decision = runtime.quarantine_target(
        target_type=TARGET_TOOL,
        target_name="shell_tool",
        reason="unsafe_output",
        severity="critical",
    )

    payload = decision.to_dict()

    assert payload["verified"] is True
    assert payload["execution_allowed"] is False
    assert payload["enforcement_action"] == ACTION_QUARANTINE
    assert payload["quarantine_records"][0]["status"] == QUARANTINE_STATUS_ACTIVE


def test_quarantine_layer_sandboxes_high_risk_mutation():
    runtime = RuntimeQuarantineLayer()

    decision = runtime.quarantine_target(
        target_type=TARGET_MUTATION,
        target_name="self_modify",
        reason="runtime_corruption",
        severity="high",
    )

    assert decision.execution_allowed is True
    assert decision.enforcement_action == ACTION_SANDBOX_ONLY


def test_quarantine_layer_requires_approval_for_medium_risk():
    runtime = RuntimeQuarantineLayer()

    decision = runtime.quarantine_target(
        target_type=TARGET_BRANCH,
        target_name="experimental_branch",
        reason="replay_divergence",
        severity="medium",
    )

    assert decision.execution_allowed is True
    assert decision.enforcement_action == ACTION_REQUIRE_APPROVAL


def test_quarantine_layer_detects_active_quarantine():
    runtime = RuntimeQuarantineLayer()

    runtime.quarantine_target(
        target_type=TARGET_TOOL,
        target_name="unsafe_tool",
        reason="bad_output",
        severity="critical",
    )

    assert runtime.is_quarantined(
        target_type=TARGET_TOOL,
        target_name="unsafe_tool",
    ) is True


def test_quarantine_layer_can_release_quarantine():
    runtime = RuntimeQuarantineLayer()

    decision = runtime.quarantine_target(
        target_type=TARGET_TOOL,
        target_name="shell_tool",
        reason="unsafe_output",
        severity="critical",
    )

    quarantine_id = decision.quarantine_records[0]["quarantine_id"]

    released = runtime.release_quarantine(
        quarantine_id=quarantine_id,
    )

    payload = released.to_dict()

    assert payload["quarantined"] is False
    assert payload["execution_allowed"] is True
    assert payload["quarantine_records"][0]["status"] == QUARANTINE_STATUS_RELEASED
