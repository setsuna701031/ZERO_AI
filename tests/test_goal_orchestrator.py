from pathlib import Path

from core.goals import (
    GoalLifecyclePolicy,
    GoalOrchestrator,
    GoalProgress,
    GoalRepository,
    GoalResumePoint,
    PersistentGoal,
    PersistentSubgoal,
)


def _repository(tmp_path: Path, *, goal_status: str = "active") -> GoalRepository:
    repository = GoalRepository(tmp_path)
    repository.append_goal(PersistentGoal("goal-1", "Ship feature", status=goal_status))
    return repository


def test_no_active_subgoal_starts_first_pending_without_writing(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.append_subgoal(PersistentSubgoal("second", "goal-1", "Second", order=2))
    repository.append_subgoal(PersistentSubgoal("first", "goal-1", "First", order=1))
    before = repository.storage_path.read_bytes()

    decision = GoalOrchestrator(repository).decide("goal-1")

    assert decision.action == "start_subgoal"
    assert decision.subgoal_id == "first"
    assert decision.requires_user_review is False
    assert repository.storage_path.read_bytes() == before


def test_active_subgoal_continues(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.append_subgoal(PersistentSubgoal("active", "goal-1", "Active", status="active"))
    repository.record_progress(GoalProgress("goal-1", active_subgoal_id="active"))

    assert GoalOrchestrator(repository).decide("goal-1").action == "continue"


def test_blocked_subgoal_waits_and_is_not_auto_repaired(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.append_subgoal(
        PersistentSubgoal("blocked", "goal-1", "Blocked", status="blocked", blocked_reason="contract drift")
    )

    decision = GoalOrchestrator(repository).decide("goal-1")

    assert decision.action == "wait_blocked"
    assert decision.reason == "contract drift"
    assert decision.requires_user_review is True
    assert repository.get_subgoal("blocked")["status"] == "blocked"


def test_resume_point_only_produces_resume_decision_when_policy_allows(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    point = GoalResumePoint("goal-1", "blocked", "task-1", "step-1")
    repository.append_subgoal(PersistentSubgoal("blocked", "goal-1", "Blocked", status="blocked", resume_point=point))
    policy = GoalLifecyclePolicy(allow_resume_blocked_subgoal=True, require_review_before_resume=True)

    decision = GoalOrchestrator(repository, policy=policy).decide("goal-1")

    assert decision.action == "resume_subgoal"
    assert decision.resume_point["task_id"] == "task-1"
    assert decision.requires_user_review is True
    assert repository.get_subgoal("blocked")["status"] == "blocked"


def test_all_subgoals_completed_produces_reviewed_completion_decision(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.append_subgoal(PersistentSubgoal("done", "goal-1", "Done", status="completed", progress=1.0))
    repository.record_progress(GoalProgress("goal-1", active_subgoal_id="done", completed_subgoals=["done"], progress_ratio=1.0))

    decision = GoalOrchestrator(repository).decide("goal-1")

    assert decision.action == "complete_goal"
    assert decision.requires_user_review is True
    assert repository.get_goal("goal-1")["status"] == "active"
    no_review = GoalOrchestrator(
        repository,
        policy=GoalLifecyclePolicy(require_review_before_goal_completion=False),
    ).decide("goal-1")
    assert no_review.requires_user_review is False


def test_contract_violation_blocks_without_repair(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.append_subgoal(PersistentSubgoal("pending", "goal-1", "Pending"))

    decision = GoalOrchestrator(repository).decide("goal-1", contract_violation="runtime ownership drift")

    assert decision.action == "wait_blocked"
    assert decision.requires_user_review is True
    assert repository.get_subgoal("pending")["status"] == "pending"
