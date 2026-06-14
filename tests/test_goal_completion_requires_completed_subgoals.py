from __future__ import annotations

from core.goals.goal_state_machine import GoalStateMachine
from core.goals.goal_transition import GoalTransition
from core.goals.goal_completion_authority import GoalCompletionAuthority
from core.evidence import EvidenceRecord, EvidenceValidator


def _evidence():
    return EvidenceValidator().validate(EvidenceRecord("evidence_a", "goal_a", None, "test", "ok", "now"))


def test_goal_completion_requires_completed_subgoals() -> None:
    result = GoalCompletionAuthority().complete_goal(
        goal_id="goal_a",
        reason="subgoals_not_done",
        evidence_refs=[_evidence()],
        all_subgoals_completed=False,
    )

    assert result.accepted is False
    assert "completed_goal_requires_completed_subgoals" in (result.blocked_reason or "")


def test_goal_completion_requires_explicit_subgoal_completion_flag() -> None:
    result = GoalCompletionAuthority().complete_goal(
        goal_id="goal_a",
        reason="missing_subgoal_flag",
        evidence_refs=[_evidence()],
    )

    assert result.accepted is False
    assert "completed_goal_requires_completed_subgoals" in (result.blocked_reason or "")
