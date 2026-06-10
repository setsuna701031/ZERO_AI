from __future__ import annotations

from core.goals.goal_state_machine import GoalStateMachine
from core.goals.goal_transition import GoalTransition


def test_goal_completion_requires_evidence_refs() -> None:
    result = GoalStateMachine().transition(
        GoalTransition(
            target_type="goal",
            target_id="goal_a",
            from_state="active",
            to_state="completed",
            action="complete",
            reason="missing_evidence",
            evidence_refs=[],
        ),
        all_subgoals_completed=True,
    )

    assert result.accepted is False
    assert "completed_goal_requires_evidence" in (result.blocked_reason or "")


def test_goal_completion_accepts_non_empty_evidence_refs_when_subgoals_complete() -> None:
    result = GoalStateMachine().transition(
        GoalTransition(
            target_type="goal",
            target_id="goal_a",
            from_state="active",
            to_state="completed",
            action="complete",
            reason="has_evidence",
            evidence_refs=[{"evidence_id": "evidence_a", "validation_state": "validated"}],
        ),
        all_subgoals_completed=True,
    )

    assert result.accepted is True
