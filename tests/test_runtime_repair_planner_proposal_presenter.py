from core.display.runtime_repair_planner_proposal_presenter import (
    format_runtime_repair_planner_proposal,
)


def test_runtime_repair_planner_proposal_presenter_formats_payload_fields():
    proposal = {
        "task_id": "task_001",
        "status": "failed",
        "proposal_type": "runtime_repair_planner_proposal",
        "proposal_mode": "review_only",
        "proposal_allowed": True,
        "planner_allowed": True,
        "requires_confirmation": True,
        "reason": "confirmation required",
        "human_summary": "Planner proposal is available.",
        "repair_intent": {
            "intent_type": "inspect_code_execution_failure",
            "source": "runtime_repair_planner_bridge",
            "scope": "code_execution_review",
            "risk": "high",
            "mode": "manual_review",
            "mutation_allowed": False,
            "execution_allowed": False,
        },
        "proposed_actions": ["inspect_trace", "propose_repair_plan"],
        "blocked_actions": ["schedule_task", "apply_patch"],
        "inspection_targets": ["trace.json", "execution_log.json"],
    }

    text = format_runtime_repair_planner_proposal(proposal)

    assert "Runtime Repair Planner Proposal:" in text
    assert "task_id: task_001" in text
    assert "proposal_mode: review_only" in text
    assert "proposal_allowed: True" in text
    assert "repair_intent:" in text
    assert "inspect_code_execution_failure" in text
    assert "mutation_allowed: False" in text
    assert "proposed_actions:" in text
    assert "propose_repair_plan" in text
    assert "blocked_actions:" in text
    assert "schedule_task" in text
    assert "inspection_targets:" in text
    assert "trace.json" in text


def test_runtime_repair_planner_proposal_presenter_handles_invalid_input():
    text = format_runtime_repair_planner_proposal(None)

    assert "Runtime Repair Planner Proposal:" in text
