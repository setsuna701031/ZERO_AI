from core.agent.runtime_goal_controller import RuntimeGoalController
from core.agent.runtime_goal_daemon import GoalDaemon

NOW = "2026-07-13T00:00:00Z"


def test_restart_reuses_entry_session_and_completed_mutation(tmp_path):
    controller = RuntimeGoalController(workspace_root=tmp_path, now=NOW); goal = controller.create("建立文件專案", now=NOW); goal_id = goal["goal_id"]
    daemon = GoalDaemon(controller, now=NOW); daemon.run_cycle(now=NOW)
    current = controller.show(goal_id); milestone_id = current["progress"]["waiting_approval_milestones"][0]; entry_id = current["milestones"][milestone_id]["mission_entry_ids"][0]; entry = controller.agent.show(entry_id); session_id = entry["mission_session_id"]
    restarted_controller = RuntimeGoalController(workspace_root=tmp_path, state_root=controller.agent_state_root, now=NOW); restarted = GoalDaemon(restarted_controller, state_path=daemon.state_path, now=NOW)
    restarted.run_cycle(now=NOW); assert len(restarted_controller.agent.list()) == 1 and restarted_controller.agent.show(entry_id)["mission_session_id"] == session_id
    restarted_controller.approve(goal_id, milestone_id, operator_id="operator", now=NOW); marker = tmp_path / "PROJECT.md"; timestamp = marker.stat().st_mtime_ns
    restarted.run_cycle(now=NOW); assert milestone_id in restarted_controller.show(goal_id)["progress"]["completed_milestones"]
    restarted.run_cycle(now=NOW); assert restarted_controller.agent.show(entry_id)["mission_session_id"] == session_id and marker.stat().st_mtime_ns == timestamp


def test_paused_stopped_cancelled_and_completed_goals_are_excluded(tmp_path):
    controller = RuntimeGoalController(workspace_root=tmp_path, now=NOW)
    roots = []
    for name in ("pause", "stop", "cancel"):
        root = tmp_path / name; root.mkdir(); goal = controller.create(f"建立{name}文件專案", target_root=root, now=NOW); getattr(controller, name)(goal["goal_id"], now=NOW); roots.append(goal["goal_id"])
    daemon = GoalDaemon(controller, now=NOW); cycle = daemon.run_cycle(now=NOW).to_dict()
    assert not set(roots).intersection(cycle["selected_goal_ids"])
    assert controller.agent.list() == []
