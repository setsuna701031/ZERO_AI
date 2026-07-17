import json
from pathlib import Path

from core.goals import GoalRepository, PersistentGoal, PersistentSubgoal


def test_repository_create_update_and_reload(tmp_path: Path) -> None:
    repository = GoalRepository(tmp_path)
    repository.append_goal(PersistentGoal("goal-1", "Build layer"))
    repository.append_subgoal(PersistentSubgoal("subgoal-1", "goal-1", "Persist state"))
    repository.update_goal_status("goal-1", "active")
    repository.update_subgoal_status("subgoal-1", "blocked", blocked_reason="waiting for evidence")

    reloaded = GoalRepository(tmp_path)
    assert reloaded.get_goal("goal-1")["status"] == "active"
    assert reloaded.list_subgoals("goal-1")[0]["blocked_reason"] == "waiting for evidence"
    assert repository.storage_path == tmp_path / "runtime" / "goals" / "goals.jsonl"
    assert len(repository.storage_path.read_text(encoding="utf-8").splitlines()) == 4
    assert all(json.loads(line)["schema"] == "zero.persistent_goal_event.v1" for line in repository.storage_path.read_text(encoding="utf-8").splitlines())
