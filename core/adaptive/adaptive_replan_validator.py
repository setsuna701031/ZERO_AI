from __future__ import annotations

"""Validator for Adaptive Replan loop transitions."""

import copy
from dataclasses import dataclass
from typing import Any, Mapping

from core.adaptive.adaptive_replan_state import clean_adaptive_replan_state
from core.adaptive.adaptive_replan_transition import AdaptiveReplanTransition


ADAPTIVE_REPLAN_VALIDATION_SCHEMA = "zero.adaptive_replan_validation.v1"

ALLOWED_TRANSITIONS = frozenset({
    ("continue", "continue"),
    ("continue", "replan"),
    ("continue", "blocked"),
    ("continue", "complete"),
    ("continue", "wait_for_user"),
    ("continue", "refuse"),
    ("continue", "stop"),
    ("replan", "stop"),
    ("blocked", "stop"),
    ("wait_for_user", "stop"),
    ("refuse", "stop"),
    ("complete", "stop"),
})

TERMINAL_STATES = frozenset({"complete", "blocked", "wait_for_user", "refuse", "stop"})


@dataclass(frozen=True)
class AdaptiveReplanValidationResult:
    accepted: bool
    from_state: str
    to_state: str
    reason: str
    blocked_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ADAPTIVE_REPLAN_VALIDATION_SCHEMA,
            "accepted": self.accepted,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "reason": self.reason,
            "blocked_reason": self.blocked_reason,
        }


class AdaptiveReplanValidator:
    def validate(self, transition: AdaptiveReplanTransition | Mapping[str, Any]) -> AdaptiveReplanValidationResult:
        if isinstance(transition, AdaptiveReplanTransition):
            record = transition.to_dict()
        elif isinstance(transition, Mapping):
            record = copy.deepcopy(dict(transition))
        else:
            raise TypeError("adaptive_replan_transition_must_be_mapping_or_transition")
        try:
            from_state = clean_adaptive_replan_state(record.get("from_state"))
            to_state = clean_adaptive_replan_state(record.get("to_state"))
        except ValueError as exc:
            return AdaptiveReplanValidationResult(
                accepted=False,
                from_state=str(record.get("from_state") or ""),
                to_state=str(record.get("to_state") or ""),
                reason="invalid_adaptive_replan_state",
                blocked_reason=str(exc),
            )
        if (from_state, to_state) not in ALLOWED_TRANSITIONS:
            return AdaptiveReplanValidationResult(
                accepted=False,
                from_state=from_state,
                to_state=to_state,
                reason="adaptive_replan_transition_rejected",
                blocked_reason=f"illegal_transition:{from_state}->{to_state}",
            )
        return AdaptiveReplanValidationResult(
            accepted=True,
            from_state=from_state,
            to_state=to_state,
            reason=f"adaptive_replan_transition_accepted:{from_state}->{to_state}",
        )


__all__ = [
    "ADAPTIVE_REPLAN_VALIDATION_SCHEMA",
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATES",
    "AdaptiveReplanValidationResult",
    "AdaptiveReplanValidator",
]
