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
import pytest

from core.agent.runtime_goal_controller import RuntimeGoalController


pytestmark = [pytest.mark.integration, pytest.mark.slow]


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
            if isinstance(node, ast.Import): imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module: imports.add(node.module)
    assert not any(name.startswith(("core.runtime", "core.adaptive", "core.memory", "core.agent", "core.tools")) for name in imports)


def test_max_subgoals_per_cycle_limits_context_selection(tmp_path: Path) -> None:
    repository = GoalRepository(tmp_path)
    repository.append_goal(PersistentGoal("goal-1", "Ship feature", status="active"))
    for order in range(1, 4): repository.append_subgoal(PersistentSubgoal(f"subgoal-{order}", "goal-1", f"Subgoal {order}", order=order))
    orchestrator = GoalOrchestrator(repository, policy=GoalLifecyclePolicy(max_subgoals_per_cycle=2))
    contexts = orchestrator.build_execution_contexts("goal-1")
    decision = orchestrator.decide("goal-1")
    assert [context.subgoal_id for context in contexts] == ["subgoal-1", "subgoal-2"]
    assert decision.subgoal_id == "subgoal-1"

NOW = "2026-07-13T00:00:00Z"


def test_real_static_site_goal_closes_through_existing_runtime(tmp_path):
    controller = RuntimeGoalController(workspace_root=tmp_path, now=NOW)
    goal = controller.create("完成一個簡單網站，包含首頁、樣式與驗證", now=NOW); goal_id = goal["goal_id"]
    sessions = {}; approvals = 0
    for minute in range(12):
        result = controller.run(goal_id, max_milestones=2, max_missions=10, max_iterations=30, now=f"2026-07-13T00:{minute:02d}:00Z")
        current = controller.show(goal_id)
        if current["goal_status"] == "waiting_for_approval":
            milestone_id = current["progress"]["waiting_approval_milestones"][0]; entry_id = current["milestones"][milestone_id]["mission_entry_ids"][0]
            before = controller.agent.show(entry_id); sessions[entry_id] = before["mission_session_id"]
            controller.approve(goal_id, milestone_id, operator_id="local-operator", now=f"2026-07-13T00:{minute:02d}:30Z")
            assert controller.agent.show(entry_id)["mission_session_id"] == sessions[entry_id]; approvals += 1
        if controller.show(goal_id)["goal_status"] == "completed": break
    completed = controller.show(goal_id)
    assert result["goal_id"] == goal_id and completed["goal_status"] == "completed" and completed["progress"]["completion_percentage"] == 100.0
    assert approvals == 3 and (tmp_path / "index.html").is_file() and (tmp_path / "styles.css").is_file()
    assert completed["reflection_reference"] and completed["experience_reference"] and controller.agent.load_state()["agent_status"] == "idle"
    timestamps = {path.name: path.stat().st_mtime_ns for path in (tmp_path / "index.html", tmp_path / "styles.css")}; entry_count = len(controller.agent.list()); persisted_updated = completed["updated_at"]
    resumed = controller.run(goal_id, now="2026-07-14T00:00:00Z")
    assert resumed["stopped_reason"] == "terminal" and len(controller.agent.list()) == entry_count
    assert controller.show(goal_id)["updated_at"] == persisted_updated and {path.name: path.stat().st_mtime_ns for path in (tmp_path / "index.html", tmp_path / "styles.css")} == timestamps
    second_root = tmp_path / "second-site"; second_root.mkdir()
    second = controller.create("完成第二個簡單網站，包含首頁、樣式與驗證", target_root=second_root, now="2026-07-14T00:01:00Z")
    assert "validate_content" in [second["milestones"][key]["milestone_key"] for key in second["milestone_order"]]
    assert all(second["milestones"][key]["approval_expected"] for key in second["milestone_order"][1:4]) and not any(second_root.iterdir())


def test_second_similar_goal_references_existing_memory_without_approval_bypass(tmp_path):
    controller = RuntimeGoalController(workspace_root=tmp_path, now=NOW)
    first = controller.create("完成一個簡單網站，包含首頁、樣式與驗證", now=NOW)
    # Seed a directly relevant completed Goal experience through the same terminal recorder.
    seeded = controller.show(first["goal_id"]); seeded["goal_status"] = "completed"; seeded["milestones"] = {}; seeded["milestone_order"] = []; seeded["progress"] = {"total_milestones": 0, "completed_milestones": [], "running_milestones": [], "waiting_approval_milestones": [], "blocked_milestones": [], "failed_milestones": [], "cancelled_milestones": [], "completion_percentage": 100.0, "current_milestone_id": None, "next_ready_milestone_ids": []}
    controller._record_terminal_experience(seeded, now=NOW)
    # Use an independent controller target so deterministic identity differs while memory remains shared.
    second_root = tmp_path / "site-two"; second_root.mkdir()
    second = controller.create("完成第二個簡單網站，包含首頁、樣式與驗證", target_root=second_root, now=NOW)
    assert second["goal_status"] == "ready" and all(second["milestones"][key]["approval_expected"] for key in second["milestone_order"][1:4])
    assert "validate_content" in [second["milestones"][key]["milestone_key"] for key in second["milestone_order"]]
    assert controller.agent.memory_search(second["normalized_goal"])["matches"]
    assert second["target_root"] == str(second_root.resolve()) and not (second_root / "index.html").exists()
