from core.goals import GoalStateValidator, GoalTransition


def test_resumable_requires_resume_point() -> None:
    result = GoalStateValidator().validate(
        GoalTransition("goal", "goal-1", "blocked", "resumable", "resume_ready")
    )
    assert result.valid is False
    assert "resumable_requires_resume_point" in result.violations
    assert result.requires_user_review is True


def test_completed_goal_requires_evidence_and_completed_subgoals() -> None:
    result = GoalStateValidator().validate(
        GoalTransition("goal", "goal-1", "active", "completed", "complete"),
        all_subgoals_completed=False,
    )
    assert result.valid is False
    assert "completed_goal_requires_evidence" in result.violations
    assert "completed_goal_requires_completed_subgoals" in result.violations
