from __future__ import annotations

from core.goals.goal_state_machine import GoalStateMachine
from core.goals.goal_transition import GoalTransition


def test_goal_completion_requires_completed_subgoals() -> None:
    result = GoalStateMachine().transition(
        GoalTransition(
            target_type="goal",
            target_id="goal_a",
            from_state="active",
            to_state="completed",
            action="complete",
            reason="subgoals_not_done",
            evidence_refs=[{"evidence_id": "evidence_a", "validation_state": "validated"}],
        ),
        all_subgoals_completed=False,
    )

    assert result.accepted is False
    assert "completed_goal_requires_completed_subgoals" in (result.blocked_reason or "")


def test_goal_completion_requires_explicit_subgoal_completion_flag() -> None:
    result = GoalStateMachine().transition(
        GoalTransition(
            target_type="goal",
            target_id="goal_a",
            from_state="active",
            to_state="completed",
            action="complete",
            reason="missing_subgoal_flag",
            evidence_refs=[{"evidence_id": "evidence_a", "validation_state": "validated"}],
        )
    )

    assert result.accepted is False
    assert "completed_goal_requires_completed_subgoals" in (result.blocked_reason or "")
