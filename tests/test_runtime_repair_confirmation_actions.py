from __future__ import annotations

from core.tasks.runtime_repair_confirmation_actions import (
    approve_runtime_repair_confirmation,
    build_runtime_repair_confirmation_action,
    build_runtime_repair_confirmation_action_result,
    reject_runtime_repair_confirmation,
)


def _base_confirmation():
    return {
        "task_id": "task_001",
        "proposal_id": "proposal_001",
        "confirmation_status": "pending",
        "planner_allowed_after_confirmation": True,
        "mutation_allowed_after_confirmation": False,
        "execution_allowed_after_confirmation": False,
    }


def test_approve_confirmation_keeps_mutation_execution_and_schedule_disabled():
    result = approve_runtime_repair_confirmation(
        _base_confirmation(),
        operator="tester",
        reason="looks safe for preview",
    )

    assert result["ok"] is True
    assert result["action_ok"] is True
    assert result["confirmation_status"] == "approved"
    assert result["confirmation_action"] == "approve"
    assert result["planner_allowed_after_confirmation"] is True

    assert result["mutation_allowed"] is False
    assert result["execution_allowed"] is False
    assert result["schedule_allowed"] is False
    assert result["allowed_next_action"] == "build_planner_route_preview"
    assert result["required_next_gate"] == "mutation_authorization"
    assert result["history"][-1]["operator"] == "tester"


def test_reject_confirmation_blocks_planner_mutation_execution_and_schedule():
    result = reject_runtime_repair_confirmation(
        _base_confirmation(),
        operator="tester",
        reason="not safe",
    )

    assert result["ok"] is True
    assert result["action_ok"] is True
    assert result["confirmation_status"] == "rejected"
    assert result["confirmation_action"] == "reject"
    assert result["planner_allowed_after_confirmation"] is False

    assert result["mutation_allowed"] is False
    assert result["execution_allowed"] is False
    assert result["schedule_allowed"] is False
    assert result["allowed_next_action"] == "inspect_bridge_reason"
    assert result["required_next_gate"] == "none"


def test_invalid_confirmation_action_is_rejected_without_side_effect_permission():
    result = build_runtime_repair_confirmation_action(
        _base_confirmation(),
        action="execute",
        operator="tester",
    )

    assert result["ok"] is False
    assert result["action_ok"] is False
    assert result["error_type"] == "invalid_confirmation_action"
    assert result["mutation_allowed"] is False
    assert result["execution_allowed"] is False
    assert result["schedule_allowed"] is False
    assert "approve" in result["valid_actions"]
    assert "reject" in result["valid_actions"]


def test_terminal_confirmation_state_cannot_be_changed():
    confirmation = _base_confirmation()
    confirmation["confirmation_status"] = "approved"

    result = reject_runtime_repair_confirmation(confirmation, operator="tester")

    assert result["ok"] is False
    assert result["action_ok"] is False
    assert result["error_type"] == "terminal_confirmation_state"
    assert result["confirmation_status"] == "approved"
    assert result["mutation_allowed"] is False
    assert result["execution_allowed"] is False
    assert result["schedule_allowed"] is False


def test_form_style_confirmation_helper_accepts_boolean_approved_field():
    approved = build_runtime_repair_confirmation_action_result(
        _base_confirmation(),
        approved=True,
        operator="tester",
    )
    rejected = build_runtime_repair_confirmation_action_result(
        _base_confirmation(),
        approved=False,
        operator="tester",
    )
    missing = build_runtime_repair_confirmation_action_result(
        _base_confirmation(),
        approved=None,
        operator="tester",
    )

    assert approved["confirmation_status"] == "approved"
    assert rejected["confirmation_status"] == "rejected"
    assert missing["ok"] is False
    assert missing["error_type"] == "invalid_confirmation_action"


def test_confirmation_action_preserves_raw_confirmation_snapshot():
    confirmation = _base_confirmation()
    result = approve_runtime_repair_confirmation(confirmation)

    assert result["raw_confirmation"]["task_id"] == "task_001"
    assert confirmation["confirmation_status"] == "pending"
