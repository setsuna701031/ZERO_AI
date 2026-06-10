import pytest

from core.goals import GoalStatus, PersistentGoal, PersistentSubgoal


def test_create_goal_and_subgoal_contracts() -> None:
    goal = PersistentGoal("goal-1", "Build persistence", "Keep goal progress")
    subgoal = PersistentSubgoal("subgoal-1", "goal-1", "Create contracts", order=1, progress=0.25)

    assert goal.to_dict()["status"] == "pending"
    assert subgoal.to_dict()["progress"] == 0.25
    assert GoalStatus.ACTIVE.value == "active"


def test_contract_rejects_invalid_status_and_progress() -> None:
    with pytest.raises(ValueError, match="goal_requires_valid_status"):
        PersistentGoal("goal-1", "Build", status="running")
    with pytest.raises(ValueError, match="subgoal_progress"):
        PersistentSubgoal("subgoal-1", "goal-1", "Build", progress=1.5)
