from __future__ import annotations

"""State vocabulary for cross-goal engineering sessions.

Session state is a passive coordination layer above engineering lifecycle state.
It does not execute runtime work, persist goals, write evidence, or touch memory.
"""

from enum import Enum
from typing import Any


class EngineeringSessionState(str, Enum):
    CREATED = "created"
    ACTIVE = "active"
    PAUSED = "paused"
    WAITING_USER = "waiting_user"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


TERMINAL_ENGINEERING_SESSION_STATES = frozenset({
    EngineeringSessionState.COMPLETED.value,
    EngineeringSessionState.FAILED.value,
    EngineeringSessionState.ARCHIVED.value,
})


def clean_engineering_session_state(value: EngineeringSessionState | str | Any) -> str:
    raw = value.value if isinstance(value, EngineeringSessionState) else str(value or "").strip().lower()
    try:
        return EngineeringSessionState(raw).value
    except ValueError as exc:
        raise ValueError("engineering_session_requires_valid_state") from exc


__all__ = [
    "EngineeringSessionState",
    "TERMINAL_ENGINEERING_SESSION_STATES",
    "clean_engineering_session_state",
]
