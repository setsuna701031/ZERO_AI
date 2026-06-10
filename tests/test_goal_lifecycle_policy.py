import pytest

from core.goals import GoalLifecyclePolicy


def test_lifecycle_policy_defaults_are_conservative_for_resume_and_completion() -> None:
    policy = GoalLifecyclePolicy()

    assert policy.allow_auto_start_next_subgoal is True
    assert policy.allow_resume_blocked_subgoal is False
    assert policy.require_review_before_resume is True
    assert policy.require_review_before_goal_completion is True
    assert policy.max_subgoals_per_cycle == 1


def test_lifecycle_policy_requires_positive_cycle_limit() -> None:
    with pytest.raises(ValueError, match="max_subgoals_per_cycle"):
        GoalLifecyclePolicy(max_subgoals_per_cycle=0)
