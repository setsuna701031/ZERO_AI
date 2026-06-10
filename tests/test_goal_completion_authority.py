from __future__ import annotations

from core.goals.goal_state_machine import GoalStateMachine
from core.goals.goal_transition import GoalTransition


def test_goal_state_machine_is_completion_authority() -> None:
    machine = GoalStateMachine()
    transition = GoalTransition(
        target_type="goal",
        target_id="goal_a",
        from_state="active",
        to_state="completed",
        action="complete",
        reason="all_work_done",
        evidence_refs=[{"evidence_id": "evidence_a", "validation_state": "validated"}],
    )

    result = machine.transition(transition, all_subgoals_completed=True)

    assert result.accepted is True
    assert result.to_state == "completed"
    assert result.evidence_refs


def test_goal_completion_rejects_without_state_machine_validation() -> None:
    transition = GoalTransition(
        target_type="goal",
        target_id="goal_a",
        from_state="active",
        to_state="completed",
        action="complete",
        reason="attempt_direct_complete",
        evidence_refs=[],
    )

    result = GoalStateMachine().transition(transition, all_subgoals_completed=True)

    assert result.accepted is False
    assert "completed_goal_requires_evidence" in (result.blocked_reason or "")
