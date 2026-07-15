from core.agent.runtime_goal_controller import RuntimeGoalController
from core.agent.runtime_goal_daemon import GoalDaemon, GoalDaemonConfig
from core.agent.runtime_goal_daemon_fairness import select_round_robin

NOW = "2026-07-13T00:00:00Z"


def test_round_robin_prevents_waiting_goal_from_starving_second_goal(tmp_path):
    controller = RuntimeGoalController(workspace_root=tmp_path, now=NOW); a_root = tmp_path / "a"; b_root = tmp_path / "b"; a_root.mkdir(); b_root.mkdir()
    a = controller.create("建立 A 文件專案", target_root=a_root, now=NOW); b = controller.create("建立 B 文件專案", target_root=b_root, now="2026-07-13T00:00:01Z")
    daemon = GoalDaemon(controller, config=GoalDaemonConfig(max_goals_per_cycle=1, max_missions_started_per_cycle=1), now=NOW)
    first = daemon.run_cycle(now=NOW).to_dict(); second = daemon.run_cycle(now="2026-07-13T00:00:02Z").to_dict()
    assert first["selected_goal_ids"] == [a["goal_id"]] and second["selected_goal_ids"] == [b["goal_id"]]
    assert controller.show(a["goal_id"])["goal_status"] == "waiting_for_approval"
    assert controller.show(b["goal_id"])["goal_status"] == "waiting_for_approval"


def test_two_goals_advance_in_same_bounded_cycle(tmp_path):
    controller = RuntimeGoalController(workspace_root=tmp_path, now=NOW)
    for name in ("a", "b"):
        root = tmp_path / name; root.mkdir(); controller.create(f"建立 {name} 文件專案", target_root=root, now=NOW)
    daemon = GoalDaemon(controller, config=GoalDaemonConfig(max_goals_per_cycle=2, max_missions_started_per_cycle=2), now=NOW); cycle = daemon.run_cycle(now=NOW).to_dict()
    assert len(cycle["selected_goal_ids"]) == 2 and cycle["mission_started_count"] == 2
    assert all(controller.show(goal_id)["goal_status"] == "waiting_for_approval" for goal_id in cycle["selected_goal_ids"])


def test_starvation_protection_selects_every_eligible_goal_over_100_cycles():
    goals = [{"goal_id": f"goal-{index}", "goal_status": "ready", "created_at": f"2026-07-13T00:00:{index:02d}Z"} for index in range(7)]
    cursor = 0; counts = {goal["goal_id"]: 0 for goal in goals}
    for _ in range(100):
        selected, cursor = select_round_robin(goals, cursor=cursor, limit=2)
        for goal in selected: counts[goal["goal_id"]] += 1
    assert all(count > 0 for count in counts.values())
    assert max(counts.values()) - min(counts.values()) <= 1
