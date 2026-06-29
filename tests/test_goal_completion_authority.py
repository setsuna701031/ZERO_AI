from __future__ import annotations

from core.goals.goal_state_machine import GoalStateMachine
from core.goals.goal_completion_authority import GoalCompletionAuthority
from core.goals.goal_transition import GoalTransition
from core.evidence import EvidenceRecord, EvidenceValidator
import pytest

pytestmark = [pytest.mark.contract]




def _evidence():
    return EvidenceValidator().validate(EvidenceRecord("evidence_a", "goal_a", None, "test", "ok", "now"))


def test_goal_state_machine_cannot_declare_completion_directly() -> None:
    machine = GoalStateMachine()
    transition = GoalTransition(
        target_type="goal",
        target_id="goal_a",
        from_state="active",
        to_state="completed",
        action="complete",
        reason="all_work_done",
        evidence_refs=[_evidence()],
    )

    result = machine.transition(transition, all_subgoals_completed=True)

    assert result.accepted is False
    assert result.blocked_reason == "canonical_completion_authority_required"


def test_goal_completion_rejects_without_state_machine_validation() -> None:
    transition = GoalTransition(
        target_type="goal",
        target_id="goal_a",
        from_state="active",
        to_state="completed",
        action="complete",
        reason="attempt_direct_complete",
        evidence_refs=[],
    )

    result = GoalCompletionAuthority().complete_goal(
        goal_id="goal_a",
        evidence_refs=[],
        all_subgoals_completed=True,
        reason="attempt_direct_complete",
    )

    assert result.accepted is False
    assert "completed_goal_requires_evidence" in (result.blocked_reason or "")
