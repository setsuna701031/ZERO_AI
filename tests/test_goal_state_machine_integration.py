from pathlib import Path

import pytest

from core.goals import GoalRepository, GoalStateMachine, PersistentGoal, PersistentSubgoal


def test_repository_uses_state_machine_when_provided(tmp_path: Path) -> None:
    repository = GoalRepository(tmp_path, state_machine=GoalStateMachine())
    repository.append_goal(PersistentGoal("goal-1", "Stateful", status="created"))
    repository.update_goal_status("goal-1", "planned")
    repository.update_goal_status("goal-1", "active")
    assert repository.get_goal("goal-1")["status"] == "active"

    with pytest.raises(ValueError, match="goal_lifecycle_contract_violation"):
        repository.update_goal_status("goal-1", "completed")
    assert repository.get_goal("goal-1")["status"] == "active"


def test_repository_without_state_machine_remains_backward_compatible(tmp_path: Path) -> None:
    repository = GoalRepository(tmp_path)
    repository.append_goal(PersistentGoal("goal-1", "Legacy"))
    repository.update_goal_status("goal-1", "active")
    assert repository.get_goal("goal-1")["status"] == "active"


def test_subgoal_transition_requires_resume_point(tmp_path: Path) -> None:
    repository = GoalRepository(tmp_path, state_machine=GoalStateMachine())
    repository.append_goal(PersistentGoal("goal-1", "Stateful", status="active"))
    repository.append_subgoal(PersistentSubgoal("sub-1", "goal-1", "Work", status="active"))
    repository.update_subgoal_status("sub-1", "blocked", blocked_reason="external dependency")
    with pytest.raises(ValueError, match="resumable_requires_resume_point"):
        repository.update_subgoal_status("sub-1", "resumable")


def test_repository_uses_existing_evidence_for_completion(tmp_path: Path) -> None:
    repository = GoalRepository(tmp_path, state_machine=GoalStateMachine())
    repository.append_goal(PersistentGoal("goal-1", "Stateful", status="active", evidence_refs=["e-1"]))
    repository.append_subgoal(PersistentSubgoal("sub-1", "goal-1", "Work", status="active"))
    repository.update_subgoal_status("sub-1", "completed")
    repository.update_goal_status("goal-1", "completed")
    assert repository.get_goal("goal-1")["status"] == "completed"


def test_repository_uses_existing_resume_point(tmp_path: Path) -> None:
    repository = GoalRepository(tmp_path, state_machine=GoalStateMachine())
    repository.append_goal(PersistentGoal("goal-1", "Stateful", status="active"))
    repository.append_subgoal(
        PersistentSubgoal(
            "sub-1",
            "goal-1",
            "Work",
            status="blocked",
            resume_point={"goal_id": "goal-1", "subgoal_id": "sub-1", "task_id": "task-1"},
        )
    )
    repository.update_subgoal_status("sub-1", "resumable")
    assert repository.get_subgoal("sub-1")["status"] == "resumable"
