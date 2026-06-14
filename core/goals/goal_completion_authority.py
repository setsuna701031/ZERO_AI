from __future__ import annotations

"""Single authority for declaring a Goal completed."""

from dataclasses import dataclass, field
from typing import Any

from core.evidence.evidence_validator import is_provenance_validated_evidence
from core.goals.goal_state_machine import GoalStateMachine, _GOAL_COMPLETION_AUTHORITY_TOKEN
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
            "evidence_refs": [
                ref.to_dict() if callable(getattr(ref, "to_dict", None)) else ref
                for ref in self.evidence_refs
            ],
        }

    def __deepcopy__(self, memo: dict[int, Any]) -> "GoalCompletionResult":
        return self


def _build_completion_attestation_boundary():
    issued_attestations: dict[int, GoalCompletionResult] = {}

    def is_accepted_goal_completion_result(value: Any, *, goal_id: str | None = None) -> bool:
        return bool(
            isinstance(value, GoalCompletionResult)
            and issued_attestations.get(id(value)) is value
            and value.schema == GOAL_COMPLETION_RESULT_SCHEMA
            and value.authority_owner == GOAL_COMPLETION_AUTHORITY_OWNER
            and value.accepted is True
            and value.completed is True
            and value.to_state == "completed"
            and value.evidence_refs
            and (goal_id is None or value.goal_id == goal_id)
        )

    class GoalCompletionAuthority:
        """The only legal Goal Completed declaration authority."""

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
                completion_authority_token=_GOAL_COMPLETION_AUTHORITY_TOKEN,
            )
            completion = GoalCompletionResult(
                accepted=result.accepted,
                goal_id=goal_id,
                from_state=result.from_state,
                to_state=result.to_state,
                reason=result.reason,
                blocked_reason=result.blocked_reason,
                requires_user_review=result.requires_user_review,
                evidence_refs=result.evidence_refs,
            )
            if (
                type(self.state_machine) is GoalStateMachine
                and completion.accepted
                and completion.from_state == "active"
                and completion.to_state == "completed"
                and all_subgoals_completed is True
                and completion.evidence_refs
                and all(is_provenance_validated_evidence(ref, goal_id=goal_id) for ref in completion.evidence_refs)
            ):
                issued_attestations[id(completion)] = completion
            return completion

    return GoalCompletionAuthority, is_accepted_goal_completion_result


GoalCompletionAuthority, is_accepted_goal_completion_result = _build_completion_attestation_boundary()
del _build_completion_attestation_boundary


__all__ = [
    "GOAL_COMPLETION_AUTHORITY_OWNER",
    "GOAL_COMPLETION_RESULT_SCHEMA",
    "GoalCompletionAuthority",
    "GoalCompletionResult",
    "is_accepted_goal_completion_result",
]
