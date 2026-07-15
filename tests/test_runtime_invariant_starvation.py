from __future__ import annotations

from core.agent.runtime_goal_daemon_fairness import select_round_robin


def test_runtime_invariant_round_robin_has_no_starvation_over_100_cycles():
    goals = [{"goal_id": f"goal-{index}", "goal_status": "ready", "created_at": f"2026-07-13T00:00:{index:02d}Z"} for index in range(7)]
    cursor = 0; counts = {goal["goal_id"]: 0 for goal in goals}
    for _ in range(100):
        selected, cursor = select_round_robin(goals, cursor=cursor, limit=2)
        for goal in selected: counts[goal["goal_id"]] += 1
    assert min(counts.values()) > 0
    assert max(counts.values()) - min(counts.values()) <= 1
