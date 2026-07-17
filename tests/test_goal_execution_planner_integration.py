import ast
from pathlib import Path

from core.agent.agent_loop import AgentLoop
from core.goals import (

    GoalExecutionContext,
    GoalExecutionPlanner,
    GoalExecutionPolicy,
    GoalOrchestrationDecision,
    GoalRepository,
    PersistentGoal,
    PersistentSubgoal,
)
from core.planning.planner import Planner
import pytest

pytestmark = [pytest.mark.integration]



class CapturingTrace:
    def __init__(self) -> None:
        self.events = []

    def log_decision(self, **kwargs) -> None:
        self.events.append(kwargs)


def test_execution_planner_does_not_write_goal_repository(tmp_path: Path) -> None:
    repository = GoalRepository(tmp_path)
    repository.append_goal(PersistentGoal("goal-1", "Ship feature", status="active"))
    repository.append_subgoal(PersistentSubgoal("subgoal-1", "goal-1", "Implement", status="active"))
    before = repository.storage_path.read_bytes()

    planner = GoalExecutionPlanner()
    plan = planner.plan(
        GoalOrchestrationDecision("continue", "goal-1", "subgoal-1", "active_subgoal"),
        execution_context=GoalExecutionContext("goal-1", "subgoal-1", "Implement", "", "active"),
    )

    assert plan.action == "create_task"
    assert repository.storage_path.read_bytes() == before


def test_resume_point_is_context_only_and_does_not_invoke_task_or_tool_objects() -> None:
    point = {"task_id": "task-1", "step_id": "step-2"}
    planner = GoalExecutionPlanner(
        policy=GoalExecutionPolicy(allow_resume_task_from_resume_point=True, require_review_before_resume=False)
    )

    plan = planner.plan(
        GoalOrchestrationDecision("resume_subgoal", "goal-1", "subgoal-1", "resume", point),
        execution_context={"title": "Resume safely", "task_manager": object(), "tool": object()},
    )

    assert plan.action == "resume_task"
    assert plan.resume_point == point


def test_planner_accepts_goal_execution_plan_and_planner_context() -> None:
    trace = CapturingTrace()
    planner = Planner(trace_logger=trace)
    execution_plan = GoalExecutionPlanner().plan(
        GoalOrchestrationDecision("start_subgoal", "goal-1", "subgoal-1", "start"),
        execution_context={"title": "Implement"},
    )

    planner.plan(user_input="", goal_execution_plan=execution_plan, planner_context={"source": "goal_execution"})

    planner_input = next(event for event in trace.events if event["title"] == "planner input")
    context = planner_input["raw"]["context"]
    assert context["goal_execution_plan"]["action"] == "create_task"
    assert context["planner_context"] == {"source": "goal_execution"}


def test_agent_loop_accepts_optional_execution_planner_without_running_it() -> None:
    execution_planner = GoalExecutionPlanner()

    loop = AgentLoop(goal_execution_planner=execution_planner)

    assert loop.goal_execution_planner is execution_planner
    assert loop.goal_repository is None


def test_goal_execution_planner_has_no_runtime_adaptive_memory_agent_or_tool_imports() -> None:
    goals_root = Path(__file__).resolve().parents[1] / "core" / "goals"
    target_files = {
        "goal_execution_policy.py",
        "goal_execution_decision.py",
        "goal_execution_planner.py",
    }
    imports: set[str] = set()
    for path in goals_root.glob("*.py"):
        if path.name not in target_files:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)

    assert not any(
        name.startswith(("core.runtime", "core.adaptive", "core.memory", "core.agent", "core.tools"))
        for name in imports
    )
