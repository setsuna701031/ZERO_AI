from __future__ import annotations

from core.goals.goal_completion_authority import GoalCompletionAuthority
from core.evidence import EvidenceRecord, EvidenceValidator


def _validated_evidence():
    return [EvidenceValidator().validate(EvidenceRecord("evidence-1", "goal-1", None, "test", "ok", "now"))]


def test_aer_final_closure_path_requires_goal_completion_authority() -> None:
    authority = GoalCompletionAuthority()

    terminal_result = authority.complete_goal(
        goal_id="goal-1",
        from_state="active",
        evidence_refs=_validated_evidence(),
        all_subgoals_completed=True,
        reason="aer_final_closure",
    )

    assert terminal_result.accepted is True
    assert terminal_result.completed is True
    assert terminal_result.reason == "aer_final_closure"
    assert terminal_result.blocked_reason is None
    assert terminal_result.evidence_refs == _validated_evidence()


def test_aer_final_closure_rejects_without_validated_evidence() -> None:
    authority = GoalCompletionAuthority()

    terminal_result = authority.complete_goal(
        goal_id="goal-1",
        from_state="active",
        evidence_refs=[
            {
                "id": "evidence-1",
                "validation_state": "pending",
            }
        ],
        all_subgoals_completed=True,
        reason="aer_final_closure",
    )

    assert terminal_result.accepted is False
    assert terminal_result.completed is False
    assert terminal_result.blocked_reason == "completed_goal_requires_validated_evidence"


def test_aer_final_closure_rejects_without_completed_subgoals() -> None:
    authority = GoalCompletionAuthority()

    terminal_result = authority.complete_goal(
        goal_id="goal-1",
        from_state="active",
        evidence_refs=_validated_evidence(),
        all_subgoals_completed=False,
        reason="aer_final_closure",
    )

    assert terminal_result.accepted is False
    assert terminal_result.completed is False
    assert terminal_result.blocked_reason == "completed_goal_requires_completed_subgoals"


def test_aer_final_closure_rejects_direct_terminal_completed_without_evidence() -> None:
    authority = GoalCompletionAuthority()

    terminal_result = authority.complete_goal(
        goal_id="goal-1",
        from_state="active",
        evidence_refs=[],
        all_subgoals_completed=True,
        reason="direct_terminal_completed_attempt",
    )

    assert terminal_result.accepted is False
    assert terminal_result.completed is False
    assert terminal_result.blocked_reason == "completed_goal_requires_evidence"


def test_aer_final_closure_rejects_illegal_state_transition() -> None:
    authority = GoalCompletionAuthority()

    terminal_result = authority.complete_goal(
        goal_id="goal-1",
        from_state="created",
        evidence_refs=_validated_evidence(),
        all_subgoals_completed=True,
        reason="illegal_direct_completion_attempt",
    )

    assert terminal_result.accepted is False
    assert terminal_result.completed is False
    assert terminal_result.blocked_reason == "transition_not_allowed"
