import ast
from pathlib import Path

from core.adaptive import AdaptivePlanner
from core.goals import GoalRepository, GoalStateMachine, PersistentGoal, PersistentSubgoal
import pytest

pytestmark = [pytest.mark.integration]




def test_state_machine_rejection_waits_for_user() -> None:
    plan = AdaptivePlanner().decide(
        current_goal={"goal_id": "goal-1", "status": "active"},
        subgoals=[{"subgoal_id": "sub-1", "status": "blocked"}],
    )
    assert plan.decision_type == "wait_for_user"
    assert "resumable_requires_resume_point" in plan.reason


def test_adaptive_planner_does_not_modify_repository(tmp_path: Path) -> None:
    repository = GoalRepository(tmp_path, state_machine=GoalStateMachine())
    repository.append_goal(PersistentGoal("goal-1", "Goal", status="active"))
    repository.append_subgoal(PersistentSubgoal("sub-1", "goal-1", "Subgoal", status="active"))
    before = repository.storage_path.read_bytes()

    plan = AdaptivePlanner(state_machine=repository.state_machine).decide(
        current_goal=repository.get_goal("goal-1"),
        subgoals=repository.list_subgoals("goal-1"),
        blocker_summary="external dependency",
    )

    assert plan.decision_type == "mark_blocked"
    assert repository.storage_path.read_bytes() == before
    assert repository.get_subgoal("sub-1")["status"] == "active"


def test_adaptive_planner_has_no_runtime_memory_or_repository_authority() -> None:
    planner_path = Path(__file__).resolve().parents[1] / "core" / "adaptive" / "adaptive_planner.py"
    tree = ast.parse(planner_path.read_text(encoding="utf-8"))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not any(name.startswith(("core.runtime", "core.memory")) for name in imports)
    assert "GoalRepository" not in planner_path.read_text(encoding="utf-8")
    assert not {"update_goal_status", "update_subgoal_status", "run_task", "execute"} & calls
