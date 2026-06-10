from __future__ import annotations

from core.goals.goal_state_machine import GoalStateMachine
from core.goals.goal_transition import GoalTransition


def test_goal_completion_rejects_pending_evidence_refs() -> None:
    result = GoalStateMachine().transition(
        GoalTransition(
            target_type="goal",
            target_id="goal_a",
            from_state="active",
            to_state="completed",
            action="complete",
            reason="pending_evidence_must_not_complete_goal",
            evidence_refs=[{"evidence_id": "evidence_pending", "validation_state": "pending"}],
        ),
        all_subgoals_completed=True,
    )

    assert result.accepted is False
    assert "completed_goal_requires_validated_evidence" in (result.blocked_reason or "")
