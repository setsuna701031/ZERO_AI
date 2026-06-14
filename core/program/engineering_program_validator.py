from __future__ import annotations

"""Validator for engineering program transitions."""

import copy
from dataclasses import dataclass
from typing import Any, Mapping

from core.program.engineering_program_state import clean_engineering_program_state
from core.program.engineering_program_transition import EngineeringProgramTransition
from core.goals.goal_completion_authority import is_accepted_goal_completion_result


ENGINEERING_PROGRAM_VALIDATION_SCHEMA = "zero.engineering_program_validation.v1"

ALLOWED_PROGRAM_TRANSITIONS = frozenset({
    ("created", "active"),
    ("created", "blocked"),
    ("created", "completed"),
    ("created", "failed"),
    ("active", "active"),
    ("active", "paused"),
    ("active", "blocked"),
    ("active", "completed"),
    ("active", "failed"),
    ("paused", "active"),
    ("paused", "failed"),
    ("blocked", "active"),
    ("blocked", "failed"),
    ("completed", "archived"),
    ("failed", "archived"),
})


@dataclass(frozen=True)
class EngineeringProgramValidationResult:
    accepted: bool
    from_state: str
    to_state: str
    reason: str
    blocked_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ENGINEERING_PROGRAM_VALIDATION_SCHEMA,
            "accepted": self.accepted,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "reason": self.reason,
            "blocked_reason": self.blocked_reason,
        }


class EngineeringProgramValidator:
    def validate(self, transition: EngineeringProgramTransition | Mapping[str, Any]) -> EngineeringProgramValidationResult:
        if isinstance(transition, EngineeringProgramTransition):
            record = transition.to_dict()
        elif isinstance(transition, Mapping):
            record = copy.deepcopy(dict(transition))
        else:
            raise TypeError("engineering_program_transition_must_be_mapping_or_transition")
        try:
            from_state = clean_engineering_program_state(record.get("from_state"))
            to_state = clean_engineering_program_state(record.get("to_state"))
        except ValueError as exc:
            return EngineeringProgramValidationResult(
                accepted=False,
                from_state=str(record.get("from_state") or ""),
                to_state=str(record.get("to_state") or ""),
                reason="invalid_engineering_program_state",
                blocked_reason=str(exc),
            )
        if (from_state, to_state) not in ALLOWED_PROGRAM_TRANSITIONS:
            return EngineeringProgramValidationResult(
                accepted=False,
                from_state=from_state,
                to_state=to_state,
                reason="engineering_program_transition_rejected",
                blocked_reason=f"illegal_transition:{from_state}->{to_state}",
            )
        if to_state == "completed" and (
            not isinstance(transition, EngineeringProgramTransition)
            or not transition.goal_id
            or not is_accepted_goal_completion_result(transition.completion_attestation, goal_id=transition.goal_id)
        ):
            return EngineeringProgramValidationResult(
                accepted=False,
                from_state=from_state,
                to_state=to_state,
                reason="engineering_program_transition_rejected",
                blocked_reason="canonical_completion_attestation_required",
            )
        return EngineeringProgramValidationResult(
            accepted=True,
            from_state=from_state,
            to_state=to_state,
            reason=f"engineering_program_transition_accepted:{from_state}->{to_state}",
        )


__all__ = [
    "ALLOWED_PROGRAM_TRANSITIONS",
    "ENGINEERING_PROGRAM_VALIDATION_SCHEMA",
    "EngineeringProgramValidationResult",
    "EngineeringProgramValidator",
]
