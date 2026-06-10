import ast
from pathlib import Path

from core.agent.agent_loop import AgentLoop
from core.goals import (
    GoalExecutionContext,
    GoalLifecyclePolicy,
    GoalOrchestrator,
    GoalRepository,
    PersistentGoal,
    PersistentSubgoal,
)
from core.planning.planner import Planner


class CapturingTrace:
    def __init__(self) -> None:
        self.events = []

    def log_decision(self, **kwargs) -> None:
        self.events.append(kwargs)


def test_planner_accepts_goal_execution_context_without_querying_repository() -> None:
    trace = CapturingTrace()
    planner = Planner(trace_logger=trace)
    context = GoalExecutionContext("goal-1", "subgoal-1", "Implement", "", "active")

    planner.plan(user_input="", goal_execution_context=context)

    planner_input = next(event for event in trace.events if event["title"] == "planner input")
    assert planner_input["raw"]["context"]["goal_execution_context"]["subgoal_id"] == "subgoal-1"


def test_agent_loop_accepts_optional_repository_and_orchestrator_without_running_them(tmp_path: Path) -> None:
    repository = GoalRepository(tmp_path)
    orchestrator = GoalOrchestrator(repository)

    loop = AgentLoop(goal_repository=repository, goal_orchestrator=orchestrator)

    assert loop.goal_repository is repository
    assert loop.goal_orchestrator is orchestrator
    assert not repository.storage_path.exists()


def test_orchestrator_has_no_execution_tool_memory_runtime_or_adaptive_imports() -> None:
    goals_root = Path(__file__).resolve().parents[1] / "core" / "goals"
    imports: set[str] = set()
    for path in goals_root.glob("*.py"):
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


def test_max_subgoals_per_cycle_limits_context_selection(tmp_path: Path) -> None:
    repository = GoalRepository(tmp_path)
    repository.append_goal(PersistentGoal("goal-1", "Ship feature", status="active"))
    for order in range(1, 4):
        repository.append_subgoal(PersistentSubgoal(f"subgoal-{order}", "goal-1", f"Subgoal {order}", order=order))
    orchestrator = GoalOrchestrator(repository, policy=GoalLifecyclePolicy(max_subgoals_per_cycle=2))

    contexts = orchestrator.build_execution_contexts("goal-1")
    decision = orchestrator.decide("goal-1")

    assert [context.subgoal_id for context in contexts] == ["subgoal-1", "subgoal-2"]
    assert decision.subgoal_id == "subgoal-1"
