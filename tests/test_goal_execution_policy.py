import pytest

from core.goals import GoalExecutionPolicy


def test_goal_execution_policy_defaults_are_conservative_for_resume_and_completion() -> None:
    policy = GoalExecutionPolicy()

    assert policy.allow_create_task_from_subgoal is True
    assert policy.allow_resume_task_from_resume_point is False
    assert policy.require_review_before_create_task is False
    assert policy.require_review_before_resume is True
    assert policy.require_review_before_complete_goal is True
    assert policy.max_execution_plans_per_cycle == 1


def test_goal_execution_policy_requires_positive_plan_limit() -> None:
    with pytest.raises(ValueError, match="max_execution_plans_per_cycle"):
        GoalExecutionPolicy(max_execution_plans_per_cycle=0)
