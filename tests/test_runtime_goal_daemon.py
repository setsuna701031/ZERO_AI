from copy import deepcopy

import pytest

from core.agent.runtime_goal_controller import RuntimeGoalController
from core.agent.runtime_goal_daemon import GoalDaemon, GoalDaemonConfig, load_goal_daemon_state, validate_goal_daemon_cycle, validate_goal_daemon_state

NOW = "2026-07-13T00:00:00Z"


@pytest.mark.parametrize(("field", "value"), [("max_goals_per_cycle", 0), ("max_missions_started_per_cycle", True), ("max_projection_updates_per_cycle", -1), ("max_replans_per_cycle", 0), ("poll_interval_seconds", 0.0)])
def test_invalid_config_fails_closed(field, value):
    values = GoalDaemonConfig().to_dict(); values[field] = value
    with pytest.raises(ValueError): GoalDaemonConfig(**values)


def test_state_and_cycle_are_sealed_atomic_and_bounded(tmp_path):
    controller = RuntimeGoalController(workspace_root=tmp_path, now=NOW); controller.create("建立文件專案", now=NOW)
    daemon = GoalDaemon(controller, config=GoalDaemonConfig(max_goals_per_cycle=1, max_missions_started_per_cycle=1), now=NOW)
    state = load_goal_daemon_state(daemon.state_path); assert validate_goal_daemon_state(state) == [] and not daemon.state_path.with_name(".goal-daemon.json.tmp").exists()
    cycle = daemon.run_cycle(now=NOW).to_dict(); assert validate_goal_daemon_cycle(cycle) == []
    assert len(cycle["selected_goal_ids"]) <= 1 and cycle["mission_started_count"] <= 1 and cycle["projection_update_count"] <= 1
    budget = cycle["runtime_mission_budget"]
    assert budget["contract"] == "zero.agent.runtime_mission_budget.v1" and budget["budget_fingerprint"]
    assert budget["active_mission_count"] <= budget["runtime_budget"] and budget["invariant_satisfied"] is True
    tampered = deepcopy(cycle); tampered["cycle_status"] = "failed"
    assert "goal_daemon_cycle_fingerprint_mismatch" in validate_goal_daemon_cycle(tampered)


def test_once_is_idempotent_for_waiting_approval_entry(tmp_path):
    controller = RuntimeGoalController(workspace_root=tmp_path, now=NOW); goal = controller.create("建立文件專案", now=NOW)
    daemon = GoalDaemon(controller, now=NOW); first = daemon.run_cycle(now=NOW).to_dict(); current = controller.show(goal["goal_id"]); entries = controller.agent.list()
    assert current["goal_status"] == "waiting_for_approval" and len(entries) == 1
    entry_id = entries[0]["entry_id"]; session_id = entries[0]["mission_session_id"]
    second = daemon.run_cycle(now=NOW).to_dict()
    assert second["mission_started_count"] == 0 and len(controller.agent.list()) == 1
    assert controller.agent.show(entry_id)["mission_session_id"] == session_id
