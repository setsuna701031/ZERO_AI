from copy import deepcopy

from core.agent.runtime_goal_controller import RuntimeGoalController
from core.agent.runtime_long_horizon_goal import seal_long_horizon_goal, seal_milestone
from core.runtime.runtime_event_bus import load_event_bus_state, replay

NOW = "2026-07-13T00:00:00Z"


def test_waiting_approval_and_completed_entry_recover_without_duplication(tmp_path):
    controller = RuntimeGoalController(workspace_root=tmp_path, now=NOW); goal = controller.create("完成一個簡單網站，包含首頁、樣式與驗證", now=NOW); goal_id = goal["goal_id"]
    controller.run(goal_id, now=NOW); waiting = controller.show(goal_id); milestone_id = waiting["progress"]["waiting_approval_milestones"][0]; entry_id = waiting["milestones"][milestone_id]["mission_entry_ids"][0]
    event_count = len(replay(load_event_bus_state(controller.agent.event_bus_path))); restarted = RuntimeGoalController(workspace_root=tmp_path, state_root=controller.agent_state_root, now=NOW)
    recovered = restarted.recover(goal_id, now=NOW)
    assert recovered["goal_status"] == "waiting_for_approval" and recovered["milestones"][milestone_id]["mission_entry_ids"] == [entry_id]
    restarted.recover(goal_id, now=NOW); assert len(restarted.agent.list()) == 1 and len(replay(load_event_bus_state(restarted.agent.event_bus_path))) == event_count
    restarted.approve(goal_id, milestone_id, operator_id="operator", now=NOW); projected = restarted.recover(goal_id, now=NOW)
    assert milestone_id in projected["progress"]["completed_milestones"]


def test_identity_mismatch_blocks_and_completed_goal_resume_is_noop(tmp_path):
    controller = RuntimeGoalController(workspace_root=tmp_path, now=NOW); goal = controller.create("建立文件專案", now=NOW); goal_id = goal["goal_id"]
    controller.run(goal_id, now=NOW); current = controller.show(goal_id); milestone_id = current["progress"]["waiting_approval_milestones"][0]; entry_id = current["milestones"][milestone_id]["mission_entry_ids"][0]
    controller.agent._update_entry_metadata(entry_id, {"goal_id": "wrong-goal"}, now=NOW)
    blocked = controller.recover(goal_id, now=NOW); assert blocked["goal_status"] == "blocked" and blocked["milestones"][milestone_id]["failure"]["reasons"] == ["long_goal_mission_identity_mismatch"]
