from __future__ import annotations

from pathlib import Path

from core.agent.runtime_goal_controller import RuntimeGoalController
from core.agent.runtime_goal_operations import GoalOperationsConfig, GoalOperationsService

NOW = "2026-07-13T00:00:00Z"
GOAL_TEXT = "Build a static website with index.html and styles.css"

def make_goal(tmp_path: Path):
    controller = RuntimeGoalController(workspace_root=tmp_path, now=NOW)
    goal = controller.create(GOAL_TEXT, now=NOW)
    service = GoalOperationsService(GoalOperationsConfig(str(tmp_path), state_root=str(controller.agent_state_root), reference_time=NOW))
    return controller, goal, service

def make_waiting_goal(tmp_path: Path):
    controller, goal, service = make_goal(tmp_path)
    controller.run(goal["goal_id"], max_milestones=1, max_missions=1, now="2026-07-13T00:01:00Z")
    return controller, controller.show(goal["goal_id"]), service

def byte_snapshot(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)).replace("\\", "/"): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}
