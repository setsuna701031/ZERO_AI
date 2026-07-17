from __future__ import annotations

"""The sole decision authority for Goal and Subgoal lifecycle transitions."""

from core.goals.goal_state_validator import GoalStateValidator
from core.goals.goal_transition import GoalTransition, GoalTransitionResult


_GOAL_COMPLETION_AUTHORITY_TOKEN = object()


class GoalStateMachine:
    def __init__(self, *, validator: GoalStateValidator | None = None) -> None:
        self.validator = validator or GoalStateValidator()

    def transition(
        self,
        transition: GoalTransition,
        *,
        all_subgoals_completed: bool | None = None,
        completion_authority_token: object | None = None,
    ) -> GoalTransitionResult:
        if (
            transition.target_type == "goal"
            and transition.to_state == "completed"
            and completion_authority_token is not _GOAL_COMPLETION_AUTHORITY_TOKEN
        ):
            return GoalTransitionResult(
                accepted=False,
                from_state=transition.from_state,
                to_state=transition.to_state,
                reason="goal_lifecycle_contract_violation",
                blocked_reason="canonical_completion_authority_required",
                requires_user_review=True,
                evidence_refs=transition.evidence_refs,
            )
        validation = self.validator.validate(
            transition,
            all_subgoals_completed=all_subgoals_completed,
        )
        if not validation.valid:
            return GoalTransitionResult(
                accepted=False,
                from_state=transition.from_state,
                to_state=transition.to_state,
                reason=validation.reason,
                blocked_reason=";".join(validation.violations),
                requires_user_review=True,
                evidence_refs=transition.evidence_refs,
            )
        return GoalTransitionResult(
            accepted=True,
            from_state=transition.from_state,
            to_state=transition.to_state,
            reason=transition.reason or "goal_lifecycle_transition_accepted",
            requires_user_review=transition.requires_user_review,
            evidence_refs=transition.evidence_refs,
        )


__all__ = ["GoalStateMachine"]
