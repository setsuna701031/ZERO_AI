from __future__ import annotations

"""Transition contract for engineering session state changes."""

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from core.session.engineering_session_state import clean_engineering_session_state


ENGINEERING_SESSION_TRANSITION_SCHEMA = "zero.engineering_session_transition.v1"


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class EngineeringSessionTransition:
    from_state: str
    to_state: str
    action: str
    reason: str = ""
    lifecycle_state: Mapping[str, Any] | None = None
    cycle: Mapping[str, Any] | None = None
    trigger: str = ""
    evidence: Mapping[str, Any] | None = None
    source: str = "engineering_session_state_machine"
    session_id: str = ""
    task_id: str = ""
    created_at: str = field(default_factory=_timestamp)
    completion_attestation: Any = None

    def __post_init__(self) -> None:
        if self.evidence is not None and not isinstance(self.evidence, Mapping):
            raise TypeError("engineering_session_transition_evidence_must_be_mapping")
        object.__setattr__(self, "from_state", clean_engineering_session_state(self.from_state))
        object.__setattr__(self, "to_state", clean_engineering_session_state(self.to_state))
        object.__setattr__(self, "action", clean_engineering_session_state(self.action))
        object.__setattr__(self, "reason", _text(self.reason))
        object.__setattr__(self, "trigger", _text(self.trigger, self.action))
        object.__setattr__(self, "evidence", _mapping(self.evidence))
        object.__setattr__(self, "source", _text(self.source, "engineering_session_state_machine"))
        object.__setattr__(self, "session_id", _text(self.session_id))
        object.__setattr__(self, "task_id", _text(self.task_id))
        object.__setattr__(self, "created_at", _text(self.created_at, _timestamp()))
        object.__setattr__(self, "lifecycle_state", _mapping(self.lifecycle_state))
        object.__setattr__(self, "cycle", _mapping(self.cycle))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ENGINEERING_SESSION_TRANSITION_SCHEMA,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "action": self.action,
            "reason": self.reason,
            "trigger": self.trigger,
            "evidence": copy.deepcopy(dict(self.evidence or {})),
            "source": self.source,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "created_at": self.created_at,
            "timestamp": self.created_at,
            "lifecycle_state": copy.deepcopy(dict(self.lifecycle_state or {})),
            "cycle": copy.deepcopy(dict(self.cycle or {})),
            "execution_path": {
                "transition_only": True,
                "executes_tasks": False,
                "persists_records": False,
                "mutates_goal_repository": False,
                "mutates_runtime": False,
                "mutates_memory": False,
            },
        }


__all__ = ["ENGINEERING_SESSION_TRANSITION_SCHEMA", "EngineeringSessionTransition"]
