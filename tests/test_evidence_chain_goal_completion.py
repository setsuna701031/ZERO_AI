from core.adaptive import AdaptivePlanner
from core.evidence import EvidenceChain, EvidenceRecord, EvidenceValidator


def _validated(evidence_id: str = "e-v") -> EvidenceRecord:
    return EvidenceValidator().validate(
        EvidenceRecord(evidence_id, "goal-1", None, "scanner", "complete", "now"),
    )


def test_validated_evidence_chain_allows_completion_suggestion() -> None:
    chain = EvidenceChain.from_records("goal-1", [_validated()])
    plan = AdaptivePlanner().decide(
        current_goal={"goal_id": "goal-1", "status": "active"},
        subgoals=[{"subgoal_id": "sub-1", "status": "completed"}],
        evidence_summary=chain,
    )
    assert plan.reason == "goal_completion_transition_ready"
    assert plan.required_transition["evidence_refs"] == ["e-v"]


def test_rejected_evidence_chain_blocks_completion_even_with_validated_evidence() -> None:
    rejected = EvidenceValidator().reject(
        EvidenceRecord("e-r", "goal-1", None, "scanner", "bad", "now"),
    )
    chain = EvidenceChain.from_records("goal-1", [_validated(), rejected])
    plan = AdaptivePlanner().decide(
        current_goal={"goal_id": "goal-1", "status": "active"},
        subgoals=[{"subgoal_id": "sub-1", "status": "completed"}],
        evidence_summary=chain,
    )
    assert plan.decision_type == "request_evidence"
    assert plan.required_transition is None


def test_serialized_validated_evidence_summary_does_not_authorize_completion() -> None:
    plan = AdaptivePlanner().decide(
        current_goal={"goal_id": "goal-1", "status": "active"},
        subgoals=[{"subgoal_id": "sub-1", "status": "completed"}],
        evidence_summary={
            "evidence_ids": ["e-v"],
            "validation_summary": {"validated": 1, "rejected": 0, "pending": 0},
        },
    )
    assert plan.reason == "goal_completion_requires_validated_evidence"
    assert plan.required_transition is None
