from pathlib import Path

from core.goals import GoalProgress, GoalRepository, PersistentGoal


def test_progress_reload_preserves_completed_and_blocked_subgoals(tmp_path: Path) -> None:
    repository = GoalRepository(tmp_path)
    repository.append_goal(PersistentGoal("goal-1", "Build layer"))
    repository.record_progress(
        GoalProgress(
            "goal-1",
            completed_subgoals=["subgoal-1"],
            blocked_subgoals=["subgoal-2"],
            progress_ratio=0.5,
        )
    )
    repository.record_progress(GoalProgress("goal-1", active_subgoal_id="subgoal-3", progress_ratio=0.75))

    progress = GoalRepository(tmp_path).get_progress("goal-1")
    assert progress["completed_subgoals"] == ["subgoal-1"]
    assert progress["blocked_subgoals"] == ["subgoal-2"]
    assert progress["active_subgoal_id"] == "subgoal-3"
