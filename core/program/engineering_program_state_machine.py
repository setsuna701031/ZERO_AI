from __future__ import annotations

"""State machine mapping engineering session state into program state.

This layer is deliberately above Session and below future portfolio/memory. It
consumes passive session records and returns passive program state only.
"""

import copy
from dataclasses import dataclass
from typing import Any, Mapping

from core.program.engineering_program_state import TERMINAL_ENGINEERING_PROGRAM_STATES
from core.program.engineering_program_transition import EngineeringProgramTransition
from core.program.engineering_program_validator import EngineeringProgramValidator


ENGINEERING_PROGRAM_STATE_MACHINE_SCHEMA = "zero.engineering_program_state_machine.v1"


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class EngineeringProgramStateResult:
    accepted: bool
    from_state: str
    to_state: str
    program_state: str
    terminal: bool
    reason: str
    blocked_reason: str = ""
    session_state: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ENGINEERING_PROGRAM_STATE_MACHINE_SCHEMA,
            "accepted": self.accepted,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "program_state": self.program_state,
            "terminal": self.terminal,
            "reason": self.reason,
            "blocked_reason": self.blocked_reason,
            "session_state": copy.deepcopy(dict(self.session_state or {})),
            "execution_path": {
                "state_machine_only": True,
                "executes_tasks": False,
                "creates_continuation": False,
                "creates_replan": False,
                "persists_records": False,
                "mutates_goal_repository": False,
                "mutates_runtime": False,
                "mutates_memory": False,
            },
        }


class EngineeringProgramStateMachine:
    def __init__(self, *, validator: EngineeringProgramValidator | None = None) -> None:
        self.validator = validator or EngineeringProgramValidator()

    def transition(self, transition: EngineeringProgramTransition | Mapping[str, Any]) -> EngineeringProgramStateResult:
        record = transition.to_dict() if isinstance(transition, EngineeringProgramTransition) else _mapping(transition)
        validation = self.validator.validate(transition)
        validation_record = validation.to_dict()
        from_state = _text(validation_record.get("from_state"))
        to_state = _text(validation_record.get("to_state"))
        session_state = _mapping(record.get("session_state"))
        if not validation.accepted:
            return EngineeringProgramStateResult(
                accepted=False,
                from_state=from_state,
                to_state=to_state,
                program_state=from_state or "failed",
                terminal=True,
                reason=_text(validation_record.get("reason"), "engineering_program_transition_rejected"),
                blocked_reason=_text(validation_record.get("blocked_reason")),
                session_state=session_state,
            )
        return EngineeringProgramStateResult(
            accepted=True,
            from_state=from_state,
            to_state=to_state,
            program_state=to_state,
            terminal=to_state in TERMINAL_ENGINEERING_PROGRAM_STATES,
            reason=_text(record.get("reason"), _text(validation_record.get("reason"), f"engineering_program_{to_state}")),
            session_state=session_state,
        )

    def evaluate_session(
        self,
        session_state: Mapping[str, Any],
        *,
        from_state: str = "created",
        cycle: Mapping[str, Any] | None = None,
        goal_id: str = "",
        completion_attestation: Any = None,
    ) -> EngineeringProgramStateResult:
        session = _mapping(session_state)
        target = self.target_state_for_session(session)
        return self.transition(
            EngineeringProgramTransition(
                from_state=from_state,
                to_state=target,
                action=target,
                reason=_text(session.get("reason"), f"engineering_program_{target}"),
                session_state=session,
                cycle=cycle,
                goal_id=_text(goal_id),
                completion_attestation=completion_attestation,
            )
        )

    def evaluate_cycle(self, cycle: Mapping[str, Any], *, from_state: str = "created") -> EngineeringProgramStateResult:
        record = _mapping(cycle)
        return self.evaluate_session(
            _mapping(record.get("engineering_session_state")),
            from_state=from_state,
            cycle=record,
            goal_id=_text(record.get("goal_id")),
            completion_attestation=record.get("goal_completion_attestation"),
        )

    @staticmethod
    def target_state_for_session(session_state: Mapping[str, Any]) -> str:
        session = _mapping(session_state)
        state = _text(session.get("session_state") or session.get("to_state"), "active").lower()
        accepted = session.get("accepted")
        if accepted is False:
            return "failed"
        if state == "completed":
            return "completed"
        if state == "failed":
            return "failed"
        if state == "blocked":
            return "blocked"
        if state == "paused":
            return "paused"
        if state in {"created", "active", "waiting_user"}:
            return "active"
        if state == "archived":
            return "archived"
        return "active"


__all__ = [
    "ENGINEERING_PROGRAM_STATE_MACHINE_SCHEMA",
    "EngineeringProgramStateMachine",
    "EngineeringProgramStateResult",
]
