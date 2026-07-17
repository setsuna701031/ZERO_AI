import pytest

from core.agent.runtime_goal_controller import RuntimeGoalController
from core.runtime.runtime_event_bus import load_event_bus_state, replay

NOW = "2026-07-13T00:00:00Z"


def make(tmp_path):
    controller = RuntimeGoalController(workspace_root=tmp_path, now=NOW)
    goal = controller.create("完成一個簡單網站，包含首頁、樣式與驗證", now=NOW)
    return controller, goal


def test_ready_generation_is_deterministic_dependency_bound_and_not_duplicated(tmp_path):
    controller, goal = make(tmp_path)
    first = controller.run(goal["goal_id"], max_milestones=1, max_missions=1, now=NOW)
    current = controller.show(goal["goal_id"]); entries = controller.agent.list()
    assert first["goal_status"] == "waiting_for_approval" and len(entries) == 1
    entry = entries[0]; milestone_id = current["progress"]["waiting_approval_milestones"][0]
    assert entry["goal_id"] == goal["goal_id"] and entry["milestone_id"] == milestone_id and entry["source"] == "long_horizon_goal"
    assert not (tmp_path / "project.marker").exists()
    controller.run(goal["goal_id"], max_milestones=1, max_missions=1, now=NOW)
    assert len(controller.agent.list()) == 1


def test_pause_resume_stop_cancel_checkpoint_and_events(tmp_path):
    controller, goal = make(tmp_path); goal_id = goal["goal_id"]
    assert controller.pause(goal_id, now=NOW)["goal_status"] == "paused"
    assert controller.run(goal_id, now=NOW)["stopped_reason"] == "pause_requested"
    assert controller.resume(goal_id, now=NOW)["goal_status"] == "ready"
    controller.run(goal_id, now=NOW); assert controller.show(goal_id)["checkpoints"]
    cancelled = controller.cancel(goal_id, now=NOW); assert cancelled["goal_status"] == "cancelled"
    topics = [event["topic"] for event in replay(load_event_bus_state(controller.agent.event_bus_path))]
    assert {"long_goal.created", "long_goal.planned", "long_goal.paused", "long_goal.resumed", "long_goal.cancelled"} <= set(topics)
    controller2 = RuntimeGoalController(workspace_root=tmp_path / "other", now=NOW); stopped_goal = controller2.create("建立文件專案", now=NOW); stopped = controller2.stop(stopped_goal["goal_id"], now=NOW)
    assert stopped["goal_status"] == "stopped"
    with pytest.raises(ValueError, match="not_paused"): controller2.resume(stopped["goal_id"], now=NOW)


def test_bounded_replan_preserves_completed_and_enforces_limit(tmp_path):
    controller, goal = make(tmp_path); goal_id = goal["goal_id"]
    controller.run(goal_id, now=NOW); current = controller.show(goal_id); blocked_id = current["progress"]["waiting_approval_milestones"][0]
    controller.approve(goal_id, blocked_id, operator_id="operator", deny=True, reason="denied", now=NOW)
    before = controller.show(goal_id); completed = list(before["progress"]["completed_milestones"]); completed_fingerprints = {key: before["milestones"][key]["milestone_fingerprint"] for key in completed}
    replanned = controller.replan(goal_id, reason="operator requested safe retry", now=NOW)
    assert replanned["replan_count"] == 1 and replanned["target_root"] == str(tmp_path.resolve()) and replanned["replan_history"]
    assert {key: replanned["milestones"][key]["milestone_fingerprint"] for key in completed} == completed_fingerprints
    limited = RuntimeGoalController(workspace_root=tmp_path / "limited", now=NOW); item = limited.create("建立文件專案", max_replans=0, now=NOW)
    with pytest.raises(ValueError, match="max_replans"): limited.replan(item["goal_id"], reason="no budget", now=NOW)
