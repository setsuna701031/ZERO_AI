from __future__ import annotations

from core.agent.runtime_goal_operations import GoalOperationsConfig, GoalOperationsService
from tests.goal_operations_test_support import make_goal


def test_runtime_invariant_budget_projection_and_health_agree(tmp_path):
    controller, _, _ = make_goal(tmp_path)
    service = GoalOperationsService(GoalOperationsConfig(str(tmp_path), state_root=str(controller.agent_state_root), runtime_budget_limit=3))
    overview = service.overview().to_dict(); health = service.health().to_dict(); budget = health["runtime_budget_status"]
    assert budget["invariant_satisfied"] is True
    assert overview["runtime_mission_budget"] == budget["runtime_budget"] == 3
    assert overview["active_mission_count"] == budget["active_mission_count"]
    assert overview["remaining_mission_capacity"] == budget["remaining_mission_capacity"]
