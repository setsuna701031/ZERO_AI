from __future__ import annotations

"""Validation rules for the sealed goal lifecycle contract."""

from dataclasses import dataclass, field
from typing import Any

from core.evidence.evidence_validator import is_provenance_validated_evidence
from core.goals.goal_state import TERMINAL_GOAL_STATES, TERMINAL_SUBGOAL_STATES
from core.goals.goal_transition import GoalTransition


@dataclass(frozen=True)
class GoalStateValidationResult:
    valid: bool
    reason: str
    violations: list[str] = field(default_factory=list)
    requires_user_review: bool = False


def _all_evidence_refs_validated(evidence_refs: list[Any], *, goal_id: str) -> bool:
    if not evidence_refs:
        return False
    return all(is_provenance_validated_evidence(ref, goal_id=goal_id) for ref in evidence_refs)


class GoalStateValidator:
    _GOAL_TRANSITIONS = {
        ("created", "planned", "plan"),
        ("planned", "active", "start"),
        ("pending", "active", "start"),
        ("blocked", "resumable", "resume_ready"),
        ("active", "completed", "complete"),
        ("created", "blocked", "block"),
        ("planned", "blocked", "block"),
        ("pending", "blocked", "block"),
        ("active", "blocked", "block"),
        ("resumable", "blocked", "block"),
        ("created", "blocked", "pause"),
        ("planned", "blocked", "pause"),
        ("pending", "blocked", "pause"),
        ("active", "blocked", "pause"),
        ("resumable", "blocked", "pause"),
        ("created", "failed", "fail"),
        ("planned", "failed", "fail"),
        ("pending", "failed", "fail"),
        ("active", "failed", "fail"),
        ("blocked", "failed", "fail"),
        ("resumable", "failed", "fail"),
    }
    _SUBGOAL_TRANSITIONS = {
        ("pending", "active", "start"),
        ("pending", "blocked", "block"),
        ("pending", "blocked", "pause"),
        ("pending", "failed", "fail"),
        ("blocked", "resumable", "resume_ready"),
        ("active", "completed", "complete"),
        ("active", "blocked", "block"),
        ("active", "blocked", "pause"),
        ("active", "failed", "fail"),
    }

    def validate(
        self,
        transition: GoalTransition,
        *,
        all_subgoals_completed: bool | None = None,
    ) -> GoalStateValidationResult:
        violations: list[str] = []
        terminal_states = TERMINAL_GOAL_STATES if transition.target_type == "goal" else TERMINAL_SUBGOAL_STATES
        allowed = self._GOAL_TRANSITIONS if transition.target_type == "goal" else self._SUBGOAL_TRANSITIONS

        if transition.from_state in terminal_states:
            violations.append(f"{transition.from_state}_state_is_terminal")
        if (transition.from_state, transition.to_state, transition.action) not in allowed:
            violations.append("transition_not_allowed")
        if transition.to_state == "resumable" and transition.resume_point is None:
            violations.append("resumable_requires_resume_point")
        if transition.to_state == "blocked" and not transition.reason:
            violations.append("blocked_requires_reason")
        if transition.target_type == "goal" and transition.to_state == "completed":
            if not transition.evidence_refs:
                violations.append("completed_goal_requires_evidence")
            elif not _all_evidence_refs_validated(transition.evidence_refs, goal_id=transition.target_id):
                violations.append("completed_goal_requires_validated_evidence")
            if all_subgoals_completed is not True:
                violations.append("completed_goal_requires_completed_subgoals")
        if transition.from_state == "resumable" and transition.to_state == "active":
            violations.append("resumable_activation_requires_runtime_adaptive")

        if violations:
            return GoalStateValidationResult(
                valid=False,
                reason="goal_lifecycle_contract_violation",
                violations=violations,
                requires_user_review=True,
            )
        return GoalStateValidationResult(valid=True, reason="goal_lifecycle_transition_valid")


__all__ = [
    "GoalStateValidationResult",
    "GoalStateValidator",
]
