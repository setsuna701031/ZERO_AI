from core.agent.runtime_goal_controller import RuntimeGoalController
from core.agent.runtime_goal_daemon import GoalDaemon, GoalDaemonConfig

NOW = "2026-07-13T00:00:00Z"


def test_two_real_website_goals_progress_across_approval_and_restart(tmp_path):
    controller = RuntimeGoalController(workspace_root=tmp_path, now=NOW); a_root = tmp_path / "site-a"; b_root = tmp_path / "site-b"; a_root.mkdir(); b_root.mkdir()
    a = controller.create("完成 A 簡單網站，包含首頁、樣式與驗證", target_root=a_root, now=NOW); b = controller.create("完成 B 簡單網站，包含首頁、樣式與驗證", target_root=b_root, now="2026-07-13T00:00:01Z")
    config = GoalDaemonConfig(max_goals_per_cycle=2, max_missions_started_per_cycle=4); daemon = GoalDaemon(controller, config=config, now=NOW); daemon.run_cycle(now=NOW)
    assert controller.show(a["goal_id"])["goal_status"] == "waiting_for_approval" and controller.show(b["goal_id"])["goal_status"] == "waiting_for_approval"
    assert len(controller.show(b["goal_id"])["progress"]["completed_milestones"]) == 1
    sessions = {}
    for goal_id in (a["goal_id"], b["goal_id"]):
        current = controller.show(goal_id); milestone_id = current["progress"]["waiting_approval_milestones"][0]; entry_id = current["milestones"][milestone_id]["mission_entry_ids"][0]; sessions[entry_id] = controller.agent.show(entry_id)["mission_session_id"]; controller.approve(goal_id, milestone_id, operator_id="operator", now=NOW)
    restarted_controller = RuntimeGoalController(workspace_root=tmp_path, state_root=controller.agent_state_root, now=NOW); restarted = GoalDaemon(restarted_controller, config=config, state_path=daemon.state_path, now=NOW)
    for minute in range(1, 20):
        restarted.run_cycle(now=f"2026-07-13T00:{minute:02d}:00Z")
        for goal_id in (a["goal_id"], b["goal_id"]):
            current = restarted_controller.show(goal_id)
            if current["goal_status"] == "waiting_for_approval":
                milestone_id = current["progress"]["waiting_approval_milestones"][0]
                for entry_id in current["milestones"][milestone_id]["mission_entry_ids"]:
                    before = restarted_controller.agent.show(entry_id); sessions.setdefault(entry_id, before["mission_session_id"])
                restarted_controller.approve(goal_id, milestone_id, operator_id="operator", now=f"2026-07-13T00:{minute:02d}:30Z")
        if all(restarted_controller.show(goal_id)["goal_status"] == "completed" for goal_id in (a["goal_id"], b["goal_id"])): break
    for goal_id, root in ((a["goal_id"], a_root), (b["goal_id"], b_root)):
        goal = restarted_controller.show(goal_id); assert goal["goal_status"] == "completed" and goal["reflection_reference"] and goal["experience_reference"]
        assert (root / "index.html").is_file() and (root / "styles.css").is_file()
    assert all(restarted_controller.agent.show(entry_id)["mission_session_id"] == session_id for entry_id, session_id in sessions.items())
    entry_count = len(restarted_controller.agent.list()); stamps = {(root.name, name): (root / name).stat().st_mtime_ns for root in (a_root, b_root) for name in ("index.html", "styles.css")}
    restarted.run_cycle(now="2026-07-14T00:00:00Z")
    assert len(restarted_controller.agent.list()) == entry_count and stamps == {(root.name, name): (root / name).stat().st_mtime_ns for root in (a_root, b_root) for name in ("index.html", "styles.css")}
