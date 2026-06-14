from core.adaptive import AdaptivePlanner
from core.evidence import EvidenceRecord, EvidenceValidator


def test_goal_completion_without_validated_evidence_is_blocked() -> None:
    plan = AdaptivePlanner().decide(
        current_goal={"goal_id": "goal-1", "status": "active"},
        subgoals=[{"subgoal_id": "sub-1", "status": "completed"}],
        evidence_summary=[],
    )
    assert plan.decision_type == "request_evidence"


def test_validated_evidence_allows_completion_suggestion() -> None:
    pending = EvidenceRecord("e-1", "goal-1", None, "scanner", "complete", "2026-06-09T00:00:00Z")
    validated = EvidenceValidator().validate(pending)
    plan = AdaptivePlanner().decide(
        current_goal={"goal_id": "goal-1", "status": "active"},
        subgoals=[{"subgoal_id": "sub-1", "status": "completed"}],
        evidence_summary=[validated],
    )
    assert plan.reason == "goal_completion_transition_ready"
    assert plan.required_transition["to_state"] == "completed"
