from __future__ import annotations

"""Transition contract for engineering session state changes."""

import copy
from dataclasses import dataclass
from typing import Any, Mapping

from core.session.engineering_session_state import clean_engineering_session_state


ENGINEERING_SESSION_TRANSITION_SCHEMA = "zero.engineering_session_transition.v1"


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class EngineeringSessionTransition:
    from_state: str
    to_state: str
    action: str
    reason: str = ""
    lifecycle_state: Mapping[str, Any] | None = None
    cycle: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "from_state", clean_engineering_session_state(self.from_state))
        object.__setattr__(self, "to_state", clean_engineering_session_state(self.to_state))
        object.__setattr__(self, "action", clean_engineering_session_state(self.action))
        object.__setattr__(self, "reason", _text(self.reason, f"engineering_session_{self.action}"))
        object.__setattr__(self, "lifecycle_state", _mapping(self.lifecycle_state))
        object.__setattr__(self, "cycle", _mapping(self.cycle))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ENGINEERING_SESSION_TRANSITION_SCHEMA,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "action": self.action,
            "reason": self.reason,
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
