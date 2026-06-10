from core.goals import (
    GoalExecutionContext,
    GoalExecutionPlanner,
    GoalExecutionPolicy,
    GoalOrchestrationDecision,
)


def _context(status: str = "active") -> GoalExecutionContext:
    return GoalExecutionContext("goal-1", "subgoal-1", "Implement feature", "Do the work", status)


def _decision(action: str, *, review: bool = False, resume_point=None) -> GoalOrchestrationDecision:
    return GoalOrchestrationDecision(
        action,
        "goal-1",
        "subgoal-1",
        f"{action} reason",
        resume_point,
        review,
        ["evidence-1"],
    )


def test_start_subgoal_produces_create_task_plan_without_creating_task() -> None:
    plan = GoalExecutionPlanner().plan(_decision("start_subgoal"), execution_context=_context("pending"))

    assert plan.action == "create_task"
    assert plan.title == "Implement feature"
    assert plan.planner_context["orchestration_action"] == "start_subgoal"


def test_continue_respects_create_task_review_policy() -> None:
    allowed = GoalExecutionPlanner().plan(_decision("continue"), execution_context=_context())
    reviewed = GoalExecutionPlanner(
        policy=GoalExecutionPolicy(require_review_before_create_task=True)
    ).plan(_decision("continue"), execution_context=_context())

    assert allowed.action == "create_task"
    assert reviewed.action == "require_review"
    assert reviewed.requires_user_review is True


def test_resume_subgoal_produces_resume_task_only_when_policy_allows() -> None:
    point = {"goal_id": "goal-1", "subgoal_id": "subgoal-1", "task_id": "task-1", "step_id": "step-2"}
    policy = GoalExecutionPolicy(
        allow_resume_task_from_resume_point=True,
        require_review_before_resume=False,
    )

    plan = GoalExecutionPlanner(policy=policy).plan(_decision("resume_subgoal", resume_point=point), execution_context=_context("blocked"))

    assert plan.action == "resume_task"
    assert plan.resume_point == point
    assert plan.planner_context["resume_point"] == point


def test_wait_blocked_never_skips_blocked_subgoal() -> None:
    point = {"task_id": "task-1"}
    policy = GoalExecutionPolicy(
        allow_create_task_from_subgoal=True,
        allow_resume_task_from_resume_point=True,
        require_review_before_resume=False,
    )

    plan = GoalExecutionPlanner(policy=policy).plan(_decision("wait_blocked", resume_point=point), execution_context=_context("blocked"))

    assert plan.action == "wait_blocked"
    assert plan.subgoal_id == "subgoal-1"


def test_complete_and_fail_goal_respect_review_without_modifying_status() -> None:
    reviewed_complete = GoalExecutionPlanner().plan(_decision("complete_goal"))
    allowed_complete = GoalExecutionPlanner(
        policy=GoalExecutionPolicy(require_review_before_complete_goal=False)
    ).plan(_decision("complete_goal"))
    reviewed_fail = GoalExecutionPlanner().plan(_decision("fail_goal", review=True))
    allowed_fail = GoalExecutionPlanner().plan(_decision("fail_goal"))

    assert reviewed_complete.action == "require_review"
    assert allowed_complete.action == "complete_goal"
    assert reviewed_fail.action == "require_review"
    assert allowed_fail.action == "fail_goal"


def test_max_execution_plans_per_cycle_limits_output() -> None:
    planner = GoalExecutionPlanner(policy=GoalExecutionPolicy(max_execution_plans_per_cycle=2))
    decisions = [_decision("start_subgoal"), _decision("continue"), _decision("wait_blocked")]

    plans = planner.plan_many(decisions)

    assert len(plans) == 2
    assert [plan.action for plan in plans] == ["create_task", "create_task"]
