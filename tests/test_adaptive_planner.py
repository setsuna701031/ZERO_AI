from core.adaptive import AdaptivePlanner, AdaptivePolicy
from core.evidence import EvidenceRecord, EvidenceValidator


def test_active_subgoal_can_continue() -> None:
    plan = AdaptivePlanner().decide(
        current_goal={"goal_id": "goal-1", "status": "active"},
        subgoals=[{"subgoal_id": "sub-1", "status": "active"}],
    )
    assert plan.decision_type == "continue_active"


def test_completed_goal_without_evidence_requests_evidence() -> None:
    plan = AdaptivePlanner().decide(
        current_goal={"goal_id": "goal-1", "status": "completed"},
        subgoals=[{"subgoal_id": "sub-1", "status": "completed"}],
    )
    assert plan.decision_type == "request_evidence"


def test_goal_with_active_subgoal_cannot_be_treated_as_completed() -> None:
    evidence = EvidenceValidator().validate(
        EvidenceRecord("e-1", "goal-1", None, "scanner", "complete", "2026-06-09T00:00:00Z"),
        accepted=True,
    )
    plan = AdaptivePlanner().decide(
        current_goal={"goal_id": "goal-1", "status": "completed"},
        subgoals=[{"subgoal_id": "sub-1", "status": "active"}],
        evidence_summary=[evidence],
    )
    assert plan.decision_type == "no_action"
    assert plan.requires_user_review is True


def test_resumable_never_continues_active() -> None:
    plan = AdaptivePlanner().decide(
        current_goal={"goal_id": "goal-1", "status": "active"},
        subgoals=[{"subgoal_id": "sub-1", "status": "resumable"}],
    )
    assert plan.decision_type == "wait_for_user"


def test_resume_requires_review_by_default_and_policy_can_disable_it() -> None:
    subgoal = {"subgoal_id": "sub-1", "status": "blocked", "resume_point": {"task_id": "task-1"}}
    strict = AdaptivePlanner().decide(current_goal={"goal_id": "goal-1", "status": "active"}, subgoals=[subgoal])
    relaxed = AdaptivePlanner(policy=AdaptivePolicy(require_review_for_resume=False)).decide(
        current_goal={"goal_id": "goal-1", "status": "active"},
        subgoals=[subgoal],
    )
    assert strict.decision_type == "resume_blocked"
    assert strict.requires_user_review is True
    assert relaxed.requires_user_review is False


def test_active_blocker_produces_valid_mark_blocked_plan() -> None:
    plan = AdaptivePlanner().decide(
        current_goal={"goal_id": "goal-1", "status": "active"},
        subgoals=[{"subgoal_id": "sub-1", "status": "active"}],
        blocker_summary={"reason": "external dependency"},
    )
    assert plan.decision_type == "mark_blocked"
    assert plan.required_transition["to_state"] == "blocked"
