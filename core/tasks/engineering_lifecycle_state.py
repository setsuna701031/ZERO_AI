from __future__ import annotations

"""State vocabulary for the engineering lifecycle boundary.

The engineering lifecycle state is a passive control vocabulary.  It does not
execute runtime work, decide adaptive actions, persist goals, write evidence, or
mutate memory.
"""

from enum import Enum
from typing import Any


class EngineeringLifecycleState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    WAITING_EVIDENCE = "waiting_evidence"
    CONTINUING = "continuing"
    REPLANNING = "replanning"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


def clean_engineering_lifecycle_state(value: EngineeringLifecycleState | str | Any) -> str:
    raw = value.value if isinstance(value, EngineeringLifecycleState) else str(value or "").strip().lower()
    try:
        return EngineeringLifecycleState(raw).value
    except ValueError as exc:
        raise ValueError("engineering_lifecycle_requires_valid_state") from exc


TERMINAL_ENGINEERING_LIFECYCLE_STATES = frozenset({
    EngineeringLifecycleState.BLOCKED.value,
    EngineeringLifecycleState.COMPLETED.value,
    EngineeringLifecycleState.FAILED.value,
})


__all__ = [
    "EngineeringLifecycleState",
    "TERMINAL_ENGINEERING_LIFECYCLE_STATES",
    "clean_engineering_lifecycle_state",
]
