from __future__ import annotations

from core.goals.goal_completion_authority import GoalCompletionAuthority, GoalCompletionResult, is_accepted_goal_completion_result
from core.goals.goal_state_machine import GoalStateMachine
from core.goals.goal_transition import GoalTransitionResult
from core.evidence import EvidenceRecord, EvidenceValidator


def _validated_evidence():
    return [EvidenceValidator().validate(EvidenceRecord("evidence-1", "goal-1", None, "test", "ok", "now"))]


def test_goal_completion_authority_accepts_validated_evidence_and_completed_subgoals() -> None:
    authority = GoalCompletionAuthority()

    result = authority.complete_goal(
        goal_id="goal-1",
        from_state="active",
        evidence_refs=_validated_evidence(),
        all_subgoals_completed=True,
    )

    assert result.accepted is True
    assert result.completed is True
    assert result.blocked_reason is None
    assert result.evidence_refs == _validated_evidence()
    assert result.to_dict()["authority_owner"].endswith(".GoalCompletionAuthority")


def test_goal_completion_authority_rejects_missing_evidence() -> None:
    authority = GoalCompletionAuthority()

    result = authority.complete_goal(
        goal_id="goal-1",
        from_state="active",
        evidence_refs=[],
        all_subgoals_completed=True,
    )

    assert result.accepted is False
    assert result.completed is False
    assert result.blocked_reason == "completed_goal_requires_evidence"


def test_goal_completion_authority_rejects_pending_evidence() -> None:
    authority = GoalCompletionAuthority()

    result = authority.complete_goal(
        goal_id="goal-1",
        from_state="active",
        evidence_refs=[
            {
                "id": "evidence-1",
                "validation_state": "pending",
            }
        ],
        all_subgoals_completed=True,
    )

    assert result.accepted is False
    assert result.completed is False
    assert result.blocked_reason == "completed_goal_requires_validated_evidence"


def test_goal_completion_authority_rejects_fabricated_evidence_ref() -> None:
    result = GoalCompletionAuthority().complete_goal(
        goal_id="goal-1",
        evidence_refs=["fabricated"],
        all_subgoals_completed=True,
    )
    assert result.accepted is False
    assert result.blocked_reason == "completed_goal_requires_validated_evidence"


def test_goal_completion_authority_rejects_self_declared_validated_mapping() -> None:
    result = GoalCompletionAuthority().complete_goal(
        goal_id="goal-1",
        evidence_refs=[{"evidence_id": "fabricated", "validation_state": "validated"}],
        all_subgoals_completed=True,
    )
    assert result.accepted is False
    assert result.blocked_reason == "completed_goal_requires_validated_evidence"


def test_directly_constructed_completion_result_is_not_canonical() -> None:
    forged = GoalCompletionResult(
        accepted=True,
        goal_id="goal-1",
        from_state="active",
        to_state="completed",
        reason="forged",
        evidence_refs=[_validated_evidence()[0]],
    )
    assert is_accepted_goal_completion_result(forged) is False


def test_goal_completion_authority_rejects_incomplete_subgoals() -> None:
    authority = GoalCompletionAuthority()

    result = authority.complete_goal(
        goal_id="goal-1",
        from_state="active",
        evidence_refs=_validated_evidence(),
        all_subgoals_completed=False,
    )

    assert result.accepted is False
    assert result.completed is False
    assert result.blocked_reason == "completed_goal_requires_completed_subgoals"


class RejectingStateMachine(GoalStateMachine):
    def transition(self, *args, **kwargs) -> GoalTransitionResult:
        return GoalTransitionResult(
            accepted=False,
            from_state="active",
            to_state="completed",
            reason="state_machine_rejected",
            blocked_reason="forced_state_machine_reject",
            requires_user_review=True,
            evidence_refs=_validated_evidence(),
        )


def test_goal_completion_authority_rejects_when_state_machine_rejects() -> None:
    authority = GoalCompletionAuthority(state_machine=RejectingStateMachine())

    result = authority.complete_goal(
        goal_id="goal-1",
        from_state="active",
        evidence_refs=_validated_evidence(),
        all_subgoals_completed=True,
    )

    assert result.accepted is False
    assert result.completed is False
    assert result.reason == "state_machine_rejected"
    assert result.blocked_reason == "forced_state_machine_reject"


class ForgingStateMachine(GoalStateMachine):
    def transition(self, *args, **kwargs) -> GoalTransitionResult:
        return GoalTransitionResult(
            accepted=True,
            from_state="active",
            to_state="completed",
            reason="forged_state_machine_acceptance",
            evidence_refs=_validated_evidence(),
        )


def test_injected_state_machine_cannot_issue_canonical_attestation() -> None:
    result = GoalCompletionAuthority(state_machine=ForgingStateMachine()).complete_goal(
        goal_id="goal-1",
        evidence_refs=_validated_evidence(),
        all_subgoals_completed=True,
    )
    assert result.accepted is True
    assert is_accepted_goal_completion_result(result) is False
