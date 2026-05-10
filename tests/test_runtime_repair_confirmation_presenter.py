from core.display.runtime_repair_confirmation_presenter import (
    format_runtime_repair_confirmation_gate,
)


def test_runtime_repair_confirmation_presenter_formats_pending_gate():
    gate = {
        "task_id": "task_001",
        "proposal_id": "proposal_001",
        "proposal_type": "runtime_repair_planner_proposal",
        "confirmation_status": "pending_confirmation",
        "requires_confirmation": True,
        "proposal_allowed": True,
        "planner_allowed_before_confirmation": False,
        "planner_allowed_after_confirmation": False,
        "mutation_allowed_after_confirmation": False,
        "execution_allowed_after_confirmation": False,
        "allowed_next_action": "request_operator_confirmation",
        "operator": "",
        "reason": "repair proposal requires confirmation before planner routing",
        "confirmation_required_fields": ["approved", "operator", "reason"],
    }

    text = format_runtime_repair_confirmation_gate(gate)

    assert "Runtime Repair Confirmation Gate:" in text
    assert "task_id: task_001" in text
    assert "proposal_id: proposal_001" in text
    assert "confirmation_status: pending_confirmation" in text
    assert "requires_confirmation: True" in text
    assert "allowed_next_action: request_operator_confirmation" in text
    assert "confirmation_required_fields:" in text
    assert "approved" in text


def test_runtime_repair_confirmation_presenter_handles_invalid_input():
    text = format_runtime_repair_confirmation_gate(None)

    assert "Runtime Repair Confirmation Gate:" in text
