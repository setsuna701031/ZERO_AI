import pytest

from core.goals import GoalExecutionPlanDecision


def test_goal_execution_plan_decision_copies_planner_and_resume_context() -> None:
    planner_context = {"title": "Implement", "nested": {"value": 1}}
    resume_point = {"task_id": "task-1", "step_id": "step-2"}
    decision = GoalExecutionPlanDecision(
        "resume_task",
        "goal-1",
        "subgoal-1",
        "approved resume",
        planner_context,
        resume_point,
        ["evidence-1"],
    )
    planner_context["nested"]["value"] = 2
    resume_point["step_id"] = "changed"

    assert decision.planner_context["nested"]["value"] == 1
    assert decision.resume_point["step_id"] == "step-2"
    assert decision.to_dict()["action"] == "resume_task"


def test_goal_execution_plan_decision_rejects_unknown_action() -> None:
    with pytest.raises(ValueError, match="goal_execution_requires_valid_action"):
        GoalExecutionPlanDecision("execute_now", "goal-1", None, "invalid")
