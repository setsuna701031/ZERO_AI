from __future__ import annotations

"""Single authority for declaring a Goal completed."""

from dataclasses import dataclass, field
from typing import Any

from core.goals.goal_state_machine import GoalStateMachine
from core.goals.goal_transition import GoalTransition


GOAL_COMPLETION_AUTHORITY_OWNER = "core.goals.goal_completion_authority.GoalCompletionAuthority"
GOAL_COMPLETION_RESULT_SCHEMA = "zero.goal_completion_authority.result.v1"


@dataclass(frozen=True)
class GoalCompletionResult:
    accepted: bool
    goal_id: str
    from_state: str
    to_state: str
    reason: str
    blocked_reason: str | None = None
    requires_user_review: bool = False
    evidence_refs: list[Any] = field(default_factory=list)
    authority_owner: str = GOAL_COMPLETION_AUTHORITY_OWNER
    schema: str = GOAL_COMPLETION_RESULT_SCHEMA

    @property
    def completed(self) -> bool:
        return self.accepted and self.to_state == "completed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "authority_owner": self.authority_owner,
            "accepted": self.accepted,
            "completed": self.completed,
            "goal_id": self.goal_id,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "reason": self.reason,
            "blocked_reason": self.blocked_reason,
            "requires_user_review": self.requires_user_review,
            "evidence_refs": list(self.evidence_refs),
        }


def is_accepted_goal_completion_result(value: Any) -> bool:
    if isinstance(value, GoalCompletionResult):
        result = value.to_dict()
    elif isinstance(value, dict):
        result = value
    else:
        return False
    return bool(
        result.get("schema") == GOAL_COMPLETION_RESULT_SCHEMA
        and result.get("authority_owner") == GOAL_COMPLETION_AUTHORITY_OWNER
        and result.get("accepted") is True
        and result.get("completed") is True
        and result.get("to_state") == "completed"
        and result.get("evidence_refs")
    )


class GoalCompletionAuthority:
    """The only legal Goal Completed declaration authority.

    This authority does not duplicate validator rules.
    It only creates the completion transition and delegates the decision to
    GoalStateMachine / GoalStateValidator.
    """

    def __init__(self, *, state_machine: GoalStateMachine | None = None) -> None:
        self.state_machine = state_machine or GoalStateMachine()

    def complete_goal(
        self,
        *,
        goal_id: str,
        from_state: str = "active",
        evidence_refs: list[Any] | None = None,
        all_subgoals_completed: bool = False,
        reason: str | None = None,
    ) -> GoalCompletionResult:
        refs = list(evidence_refs or [])

        transition = GoalTransition(
            target_type="goal",
            target_id=goal_id,
            from_state=from_state,
            to_state="completed",
            action="complete",
            reason=reason or "goal_completion_authority_requested",
            evidence_refs=refs,
        )

        result = self.state_machine.transition(
            transition,
            all_subgoals_completed=all_subgoals_completed,
        )

        return GoalCompletionResult(
            accepted=result.accepted,
            goal_id=goal_id,
            from_state=result.from_state,
            to_state=result.to_state,
            reason=result.reason,
            blocked_reason=result.blocked_reason,
            requires_user_review=result.requires_user_review,
            evidence_refs=result.evidence_refs,
        )


__all__ = [
    "GOAL_COMPLETION_AUTHORITY_OWNER",
    "GOAL_COMPLETION_RESULT_SCHEMA",
    "GoalCompletionAuthority",
    "GoalCompletionResult",
    "is_accepted_goal_completion_result",
]
