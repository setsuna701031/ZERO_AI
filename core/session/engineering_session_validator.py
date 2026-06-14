from __future__ import annotations

"""Validator for engineering session transitions."""

import copy
from dataclasses import dataclass
from typing import Any, Mapping

from core.session.engineering_session_state import TERMINAL_ENGINEERING_SESSION_STATES, clean_engineering_session_state
from core.session.engineering_session_transition import ENGINEERING_SESSION_TRANSITION_SCHEMA, EngineeringSessionTransition
from core.goals.goal_completion_authority import is_accepted_goal_completion_result


ENGINEERING_SESSION_VALIDATION_SCHEMA = "zero.engineering_session_validation.v1"

ALLOWED_SESSION_TRANSITIONS = frozenset({
    ("created", "active"),
    ("created", "blocked"),
    ("created", "failed"),
    ("active", "active"),
    ("active", "paused"),
    ("active", "waiting_user"),
    ("active", "blocked"),
    ("active", "completed"),
    ("active", "failed"),
    ("paused", "active"),
    ("paused", "failed"),
    ("waiting_user", "active"),
    ("waiting_user", "blocked"),
    ("waiting_user", "failed"),
    ("blocked", "active"),
    ("blocked", "waiting_user"),
    ("blocked", "failed"),
    ("completed", "archived"),
    ("failed", "archived"),
})


@dataclass(frozen=True)
class EngineeringSessionValidationResult:
    accepted: bool
    from_state: str
    to_state: str
    reason: str
    blocked_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ENGINEERING_SESSION_VALIDATION_SCHEMA,
            "accepted": self.accepted,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "reason": self.reason,
            "blocked_reason": self.blocked_reason,
        }


class EngineeringSessionValidator:
    def validate(self, transition: EngineeringSessionTransition | Mapping[str, Any]) -> EngineeringSessionValidationResult:
        if isinstance(transition, EngineeringSessionTransition):
            record = transition.to_dict()
        elif isinstance(transition, Mapping):
            record = copy.deepcopy(dict(transition))
        else:
            raise TypeError("engineering_session_transition_must_be_mapping_or_transition")
        try:
            from_state = clean_engineering_session_state(record.get("from_state"))
            to_state = clean_engineering_session_state(record.get("to_state"))
        except ValueError as exc:
            return EngineeringSessionValidationResult(
                accepted=False,
                from_state=str(record.get("from_state") or ""),
                to_state=str(record.get("to_state") or ""),
                reason="invalid_engineering_session_state",
                blocked_reason=str(exc),
            )
        if from_state in TERMINAL_ENGINEERING_SESSION_STATES and to_state not in TERMINAL_ENGINEERING_SESSION_STATES:
            return EngineeringSessionValidationResult(
                accepted=False,
                from_state=from_state,
                to_state=to_state,
                reason="engineering_session_terminal_transition_rejected",
                blocked_reason=f"terminal_transition:{from_state}->{to_state}",
            )
        if (from_state, to_state) not in ALLOWED_SESSION_TRANSITIONS:
            return EngineeringSessionValidationResult(
                accepted=False,
                from_state=from_state,
                to_state=to_state,
                reason="engineering_session_transition_rejected",
                blocked_reason=f"illegal_transition:{from_state}->{to_state}",
            )
        if str(record.get("schema") or "").strip() != ENGINEERING_SESSION_TRANSITION_SCHEMA:
            return EngineeringSessionValidationResult(
                accepted=False,
                from_state=from_state,
                to_state=to_state,
                reason="engineering_session_transition_rejected",
                blocked_reason="transition_schema_required",
            )
        if not isinstance(record.get("evidence"), Mapping):
            return EngineeringSessionValidationResult(
                accepted=False,
                from_state=from_state,
                to_state=to_state,
                reason="engineering_session_transition_rejected",
                blocked_reason="transition_evidence_must_be_dict",
            )
        if not str(record.get("reason") or "").strip():
            return EngineeringSessionValidationResult(
                accepted=False,
                from_state=from_state,
                to_state=to_state,
                reason="engineering_session_transition_rejected",
                blocked_reason="transition_reason_required",
            )
        if not str(record.get("trigger") or "").strip():
            return EngineeringSessionValidationResult(
                accepted=False,
                from_state=from_state,
                to_state=to_state,
                reason="engineering_session_transition_rejected",
                blocked_reason="transition_trigger_required",
            )
        if not str(record.get("source") or "").strip():
            return EngineeringSessionValidationResult(
                accepted=False,
                from_state=from_state,
                to_state=to_state,
                reason="engineering_session_transition_rejected",
                blocked_reason="transition_source_required",
            )
        if not str(record.get("created_at") or record.get("timestamp") or "").strip():
            return EngineeringSessionValidationResult(
                accepted=False,
                from_state=from_state,
                to_state=to_state,
                reason="engineering_session_transition_rejected",
                blocked_reason="transition_timestamp_required",
            )
        if not str(record.get("session_id") or record.get("task_id") or "").strip():
            return EngineeringSessionValidationResult(
                accepted=False,
                from_state=from_state,
                to_state=to_state,
                reason="engineering_session_transition_rejected",
                blocked_reason="session_identity_required",
            )
        if to_state == "completed" and (
            not isinstance(transition, EngineeringSessionTransition)
            or not is_accepted_goal_completion_result(transition.completion_attestation)
        ):
            return EngineeringSessionValidationResult(
                accepted=False,
                from_state=from_state,
                to_state=to_state,
                reason="engineering_session_transition_rejected",
                blocked_reason="canonical_completion_attestation_required",
            )
        return EngineeringSessionValidationResult(
            accepted=True,
            from_state=from_state,
            to_state=to_state,
            reason=f"engineering_session_transition_accepted:{from_state}->{to_state}",
        )


__all__ = [
    "ALLOWED_SESSION_TRANSITIONS",
    "ENGINEERING_SESSION_VALIDATION_SCHEMA",
    "EngineeringSessionValidationResult",
    "EngineeringSessionValidator",
]
