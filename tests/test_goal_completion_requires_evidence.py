from __future__ import annotations

from core.goals.goal_state_machine import GoalStateMachine
from core.goals.goal_transition import GoalTransition
from core.goals.goal_completion_authority import GoalCompletionAuthority
from core.evidence import EvidenceRecord, EvidenceValidator


def test_goal_completion_requires_evidence_refs() -> None:
    result = GoalCompletionAuthority().complete_goal(
        goal_id="goal_a",
        reason="missing_evidence",
        evidence_refs=[],
        all_subgoals_completed=True,
    )

    assert result.accepted is False
    assert "completed_goal_requires_evidence" in (result.blocked_reason or "")


def test_goal_completion_accepts_non_empty_evidence_refs_when_subgoals_complete() -> None:
    result = GoalCompletionAuthority().complete_goal(
        goal_id="goal_a",
        reason="has_evidence",
        evidence_refs=[EvidenceValidator().validate(EvidenceRecord("evidence_a", "goal_a", None, "test", "ok", "now"))],
        all_subgoals_completed=True,
    )

    assert result.accepted is True
