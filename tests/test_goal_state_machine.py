import pytest

from core.goals import GoalStateMachine, GoalTransition


def test_valid_goal_transition_is_accepted() -> None:
    result = GoalStateMachine().transition(
        GoalTransition("goal", "goal-1", "created", "planned", "plan")
    )
    assert result.accepted is True


@pytest.mark.parametrize("terminal", ["completed", "failed"])
def test_terminal_goal_cannot_reopen_or_auto_resume(terminal: str) -> None:
    result = GoalStateMachine().transition(
        GoalTransition("goal", "goal-1", terminal, "active", "start")
    )
    assert result.accepted is False
    assert result.requires_user_review is True


def test_blocked_goal_cannot_skip_to_completed() -> None:
    result = GoalStateMachine().transition(
        GoalTransition("goal", "goal-1", "blocked", "completed", "complete", evidence_refs=["e-1"]),
        all_subgoals_completed=True,
    )
    assert result.accepted is False


def test_blocked_subgoal_cannot_be_skipped() -> None:
    result = GoalStateMachine().transition(
        GoalTransition("subgoal", "sub-1", "blocked", "completed", "complete")
    )
    assert result.accepted is False


def test_resumable_to_active_does_not_bypass_runtime_adaptive() -> None:
    result = GoalStateMachine().transition(
        GoalTransition("goal", "goal-1", "resumable", "active", "start")
    )
    assert result.accepted is False
    assert "resumable_activation_requires_runtime_adaptive" in result.blocked_reason
