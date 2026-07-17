from __future__ import annotations

"""State vocabulary for engineering program lifecycle.

Program state is above session state and below future memory/portfolio layers.
It does not execute runtime work, persist records, mutate goals, or write memory.
"""

from enum import Enum
from typing import Any


class EngineeringProgramState(str, Enum):
    CREATED = "created"
    ACTIVE = "active"
    PAUSED = "paused"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


TERMINAL_ENGINEERING_PROGRAM_STATES = frozenset({
    EngineeringProgramState.COMPLETED.value,
    EngineeringProgramState.FAILED.value,
    EngineeringProgramState.ARCHIVED.value,
})


def clean_engineering_program_state(value: EngineeringProgramState | str | Any) -> str:
    raw = value.value if isinstance(value, EngineeringProgramState) else str(value or "").strip().lower()
    try:
        return EngineeringProgramState(raw).value
    except ValueError as exc:
        raise ValueError("engineering_program_requires_valid_state") from exc


__all__ = [
    "EngineeringProgramState",
    "TERMINAL_ENGINEERING_PROGRAM_STATES",
    "clean_engineering_program_state",
]
