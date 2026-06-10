from pathlib import Path

from core.goals import GoalProgress, GoalQuery, GoalRepository, GoalResumePoint, PersistentGoal


def test_goal_query_active_blocked_recent_history_and_resume_candidates(tmp_path: Path) -> None:
    repository = GoalRepository(tmp_path)
    repository.append_goal(PersistentGoal("active", "Active", status="active"))
    repository.append_goal(PersistentGoal("blocked", "Blocked", status="blocked"))
    repository.record_progress(
        GoalProgress("blocked", resume_point=GoalResumePoint("blocked", reason="continue after review"))
    )
    query = GoalQuery(repository)

    assert [goal["goal_id"] for goal in query.find_active_goals()] == ["active"]
    assert [goal["goal_id"] for goal in query.find_blocked_goals()] == ["blocked"]
    assert query.find_recent_goals(1)[0]["goal_id"] in {"active", "blocked"}
    assert len(query.find_goal_history("blocked")) == 2
    assert query.find_resume_candidates()[0]["goal_id"] == "blocked"
