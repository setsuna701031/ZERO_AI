from __future__ import annotations

"""Validator for engineering lifecycle transitions."""

import copy
from dataclasses import dataclass
from typing import Any, Mapping

from core.tasks.engineering_lifecycle_state import clean_engineering_lifecycle_state
from core.tasks.engineering_lifecycle_transition import EngineeringLifecycleTransition


ENGINEERING_LIFECYCLE_VALIDATION_SCHEMA = "zero.engineering_lifecycle_validation.v1"

ALLOWED_ENGINEERING_LIFECYCLE_TRANSITIONS = frozenset({
    ("created", "running"),
    ("created", "waiting_evidence"),
    ("created", "continuing"),
    ("created", "replanning"),
    ("created", "blocked"),
    ("created", "completed"),
    ("created", "failed"),
    ("running", "running"),
    ("running", "waiting_evidence"),
    ("running", "continuing"),
    ("running", "replanning"),
    ("running", "blocked"),
    ("running", "completed"),
    ("running", "failed"),
    ("continuing", "running"),
    ("continuing", "continuing"),
    ("continuing", "replanning"),
    ("continuing", "blocked"),
    ("continuing", "completed"),
    ("continuing", "failed"),
    ("replanning", "running"),
    ("replanning", "replanning"),
    ("replanning", "blocked"),
    ("replanning", "failed"),
    ("waiting_evidence", "running"),
    ("waiting_evidence", "waiting_evidence"),
    ("waiting_evidence", "blocked"),
    ("waiting_evidence", "failed"),
})


@dataclass(frozen=True)
class EngineeringLifecycleValidationResult:
    accepted: bool
    from_state: str
    to_state: str
    reason: str
    blocked_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ENGINEERING_LIFECYCLE_VALIDATION_SCHEMA,
            "accepted": self.accepted,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "reason": self.reason,
            "blocked_reason": self.blocked_reason,
        }


class EngineeringLifecycleValidator:
    def validate(self, transition: EngineeringLifecycleTransition | Mapping[str, Any]) -> EngineeringLifecycleValidationResult:
        if isinstance(transition, EngineeringLifecycleTransition):
            record = transition.to_dict()
        elif isinstance(transition, Mapping):
            record = copy.deepcopy(dict(transition))
        else:
            raise TypeError("engineering_lifecycle_transition_must_be_mapping_or_transition")
        try:
            from_state = clean_engineering_lifecycle_state(record.get("from_state"))
            to_state = clean_engineering_lifecycle_state(record.get("to_state"))
        except ValueError as exc:
            return EngineeringLifecycleValidationResult(
                accepted=False,
                from_state=str(record.get("from_state") or ""),
                to_state=str(record.get("to_state") or ""),
                reason="invalid_engineering_lifecycle_state",
                blocked_reason=str(exc),
            )
        if (from_state, to_state) not in ALLOWED_ENGINEERING_LIFECYCLE_TRANSITIONS:
            return EngineeringLifecycleValidationResult(
                accepted=False,
                from_state=from_state,
                to_state=to_state,
                reason="engineering_lifecycle_transition_rejected",
                blocked_reason=f"illegal_transition:{from_state}->{to_state}",
            )
        return EngineeringLifecycleValidationResult(
            accepted=True,
            from_state=from_state,
            to_state=to_state,
            reason=f"engineering_lifecycle_transition_accepted:{from_state}->{to_state}",
        )


__all__ = [
    "ALLOWED_ENGINEERING_LIFECYCLE_TRANSITIONS",
    "ENGINEERING_LIFECYCLE_VALIDATION_SCHEMA",
    "EngineeringLifecycleValidationResult",
    "EngineeringLifecycleValidator",
]
