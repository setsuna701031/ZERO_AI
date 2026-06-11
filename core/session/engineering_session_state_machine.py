from __future__ import annotations

"""State machine mapping engineering lifecycle into session state.

This layer is deliberately above Goal/Lifecycle/Adaptive and below future memory.
It consumes passive lifecycle records and returns passive session state only.
"""

import copy
from dataclasses import dataclass
from typing import Any, Mapping

from core.session.engineering_session_state import TERMINAL_ENGINEERING_SESSION_STATES, clean_engineering_session_state
from core.session.engineering_session_transition import EngineeringSessionTransition
from core.session.engineering_session_validator import ALLOWED_SESSION_TRANSITIONS, EngineeringSessionValidator


ENGINEERING_SESSION_STATE_MACHINE_SCHEMA = "zero.engineering_session_state_machine.v1"


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class EngineeringSessionStateResult:
    accepted: bool
    from_state: str
    to_state: str
    session_state: str
    terminal: bool
    reason: str
    blocked_reason: str = ""
    lifecycle_state: Mapping[str, Any] | None = None
    transition_record: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ENGINEERING_SESSION_STATE_MACHINE_SCHEMA,
            "accepted": self.accepted,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "session_state": self.session_state,
            "terminal": self.terminal,
            "reason": self.reason,
            "blocked_reason": self.blocked_reason,
            "lifecycle_state": copy.deepcopy(dict(self.lifecycle_state or {})),
            "transition_record": copy.deepcopy(dict(self.transition_record or {})),
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


class EngineeringSessionStateMachine:
    def __init__(self, *, validator: EngineeringSessionValidator | None = None) -> None:
        self.validator = validator or EngineeringSessionValidator()

    def transition(self, transition: EngineeringSessionTransition | Mapping[str, Any]) -> EngineeringSessionStateResult:
        record = transition.to_dict() if isinstance(transition, EngineeringSessionTransition) else _mapping(transition)
        validation = self.validator.validate(record)
        validation_record = validation.to_dict()
        from_state = _text(validation_record.get("from_state"))
        to_state = _text(validation_record.get("to_state"))
        lifecycle_state = _mapping(record.get("lifecycle_state"))
        if not validation.accepted:
            return EngineeringSessionStateResult(
                accepted=False,
                from_state=from_state,
                to_state=to_state,
                session_state=from_state or "failed",
                terminal=from_state in TERMINAL_ENGINEERING_SESSION_STATES,
                reason=_text(validation_record.get("reason"), "engineering_session_transition_rejected"),
                blocked_reason=_text(validation_record.get("blocked_reason")),
                lifecycle_state=lifecycle_state,
                transition_record=record,
            )
        return EngineeringSessionStateResult(
            accepted=True,
            from_state=from_state,
            to_state=to_state,
            session_state=to_state,
            terminal=to_state in TERMINAL_ENGINEERING_SESSION_STATES,
            reason=_text(record.get("reason"), _text(validation_record.get("reason"), f"engineering_session_{to_state}")),
            lifecycle_state=lifecycle_state,
            transition_record=record,
        )

    @staticmethod
    def current_state(session: Mapping[str, Any] | str) -> str:
        if isinstance(session, str):
            return clean_engineering_session_state(session)
        record = _mapping(session)
        state = record.get("session_state") or record.get("current_state") or record.get("to_state")
        return clean_engineering_session_state(state)

    @staticmethod
    def can_transition(from_state: str, to_state: str) -> bool:
        try:
            pair = (clean_engineering_session_state(from_state), clean_engineering_session_state(to_state))
        except ValueError:
            return False
        return pair in ALLOWED_SESSION_TRANSITIONS

    @staticmethod
    def is_terminal(state: Mapping[str, Any] | str) -> bool:
        try:
            return EngineeringSessionStateMachine.current_state(state) in TERMINAL_ENGINEERING_SESSION_STATES
        except ValueError:
            return False

    @staticmethod
    def build_transition_record(
        *,
        from_state: str,
        to_state: str,
        reason: str,
        trigger: str,
        evidence: Mapping[str, Any],
        source: str,
        session_id: str = "",
        task_id: str = "",
        created_at: str = "",
        lifecycle_state: Mapping[str, Any] | None = None,
        cycle: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return EngineeringSessionTransition(
            from_state=from_state,
            to_state=to_state,
            action=to_state,
            reason=reason,
            trigger=trigger,
            evidence=evidence,
            source=source,
            session_id=session_id,
            task_id=task_id,
            created_at=created_at,
            lifecycle_state=lifecycle_state,
            cycle=cycle,
        ).to_dict()

    def evaluate_lifecycle(
        self,
        lifecycle_state: Mapping[str, Any],
        *,
        from_state: str = "created",
        cycle: Mapping[str, Any] | None = None,
    ) -> EngineeringSessionStateResult:
        lifecycle = _mapping(lifecycle_state)
        cycle_record = _mapping(cycle)
        identity_sources = (cycle_record, lifecycle)
        session_id = next((_text(item.get("session_id")) for item in identity_sources if _text(item.get("session_id"))), "")
        task_id = next(
            (
                _text(item.get("task_id") or item.get("goal_id"))
                for item in identity_sources
                if _text(item.get("task_id") or item.get("goal_id"))
            ),
            "",
        )
        if not lifecycle:
            return self.transition({
                "from_state": from_state,
                "to_state": from_state,
                "reason": "missing_engineering_lifecycle_record",
                "trigger": "evaluate_lifecycle",
                "evidence": {},
                "source": "engineering_session_state_machine",
                "session_id": session_id,
                "task_id": task_id,
                "lifecycle_state": {},
                "cycle": cycle_record,
            })
        target = self.target_state_for_lifecycle(lifecycle)
        return self.transition(
            self.build_transition_record(
                from_state=from_state,
                to_state=target,
                reason=_text(lifecycle.get("reason"), f"engineering_session_{target}"),
                trigger=_text(lifecycle.get("trigger"), "engineering_lifecycle_evaluation"),
                evidence=_mapping(lifecycle.get("evidence")) or {"lifecycle_state": copy.deepcopy(lifecycle)},
                source=_text(lifecycle.get("source"), "engineering_session_state_machine"),
                session_id=session_id,
                task_id=task_id,
                lifecycle_state=lifecycle,
                cycle=cycle_record,
            )
        )

    def evaluate_cycle(self, cycle: Mapping[str, Any], *, from_state: str = "created") -> EngineeringSessionStateResult:
        record = _mapping(cycle)
        return self.evaluate_lifecycle(
            _mapping(record.get("engineering_lifecycle_state")),
            from_state=from_state,
            cycle=record,
        )

    @staticmethod
    def target_state_for_lifecycle(lifecycle_state: Mapping[str, Any]) -> str:
        lifecycle = _mapping(lifecycle_state)
        state = _text(lifecycle.get("lifecycle_state") or lifecycle.get("to_state"), "running").lower()
        accepted = lifecycle.get("accepted")
        if accepted is False:
            return "failed"
        if state in {"completed"}:
            return "completed"
        if state in {"failed"}:
            return "failed"
        if state in {"blocked"}:
            return "blocked"
        if state in {"waiting_evidence"}:
            return "waiting_user"
        if state in {"created", "running", "continuing", "replanning"}:
            return "active"
        return "active"


__all__ = [
    "ENGINEERING_SESSION_STATE_MACHINE_SCHEMA",
    "EngineeringSessionStateMachine",
    "EngineeringSessionStateResult",
]
