from __future__ import annotations

from pathlib import Path

from core.tasks.engineering_goal_runner import EngineeringGoalRunner


class FakeRepository:
    def load_goal(self, goal_id: str):
        return None


def test_engineering_goal_runner_is_bridge_not_completion_authority(tmp_path: Path) -> None:
    runner = EngineeringGoalRunner(repo_root=tmp_path, repository=FakeRepository())
    result = runner.run_goal("missing_goal")

    assert result["ok"] is False
    assert result["execution_path"]["goal_runner_bridges_only"] is True
    assert result["execution_path"]["direct_execution"] is False
    assert "goal_state" not in result
    assert result.get("adaptive_decision", {}).get("decision") == "blocked"
