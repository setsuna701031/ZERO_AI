from pathlib import Path

import pytest

from core.goals import GoalProgress, GoalRepository, GoalResumePoint, PersistentGoal


def test_resume_point_persists_without_executing_or_repairing(tmp_path: Path) -> None:
    repository = GoalRepository(tmp_path)
    repository.append_goal(PersistentGoal("goal-1", "Build layer"))
    repository.record_progress(
        GoalProgress(
            "goal-1",
            resume_point=GoalResumePoint(
                "goal-1",
                "subgoal-1",
                "task-1",
                "step-2",
                "contract violation remains blocked",
                ["evidence-1"],
            ),
        )
    )

    assert GoalRepository(tmp_path).get_resume_point("goal-1")["step_id"] == "step-2"
    with pytest.raises(ValueError, match="goal_requires_goal_id"):
        repository.record_progress({"resume_point": {"goal_id": "goal-1"}})
    assert repository.get_resume_point("goal-1")["reason"] == "contract violation remains blocked"
