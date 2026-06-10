from __future__ import annotations

from core.goals.goal_completion_authority import GoalCompletionAuthority
from core.goals.goal_state_machine import GoalStateMachine
from core.goals.goal_transition import GoalTransitionResult


VALIDATED_EVIDENCE = [
    {
        "id": "evidence-1",
        "validation_state": "validated",
    }
]


def test_goal_completion_authority_accepts_validated_evidence_and_completed_subgoals() -> None:
    authority = GoalCompletionAuthority()

    result = authority.complete_goal(
        goal_id="goal-1",
        from_state="active",
        evidence_refs=VALIDATED_EVIDENCE,
        all_subgoals_completed=True,
    )

    assert result.accepted is True
    assert result.completed is True
    assert result.blocked_reason is None
    assert result.evidence_refs == VALIDATED_EVIDENCE


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


def test_goal_completion_authority_rejects_incomplete_subgoals() -> None:
    authority = GoalCompletionAuthority()

    result = authority.complete_goal(
        goal_id="goal-1",
        from_state="active",
        evidence_refs=VALIDATED_EVIDENCE,
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
            evidence_refs=VALIDATED_EVIDENCE,
        )


def test_goal_completion_authority_rejects_when_state_machine_rejects() -> None:
    authority = GoalCompletionAuthority(state_machine=RejectingStateMachine())

    result = authority.complete_goal(
        goal_id="goal-1",
        from_state="active",
        evidence_refs=VALIDATED_EVIDENCE,
        all_subgoals_completed=True,
    )

    assert result.accepted is False
    assert result.completed is False
    assert result.reason == "state_machine_rejected"
    assert result.blocked_reason == "forced_state_machine_reject"