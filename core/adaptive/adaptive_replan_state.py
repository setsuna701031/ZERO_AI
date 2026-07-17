from __future__ import annotations

"""State vocabulary for Adaptive Replan loop control.

This module is intentionally passive.  It does not execute runtime actions,
persist records, mutate goals, or write memory.
"""

from enum import Enum
from typing import Any


class AdaptiveReplanState(str, Enum):
    CONTINUE = "continue"
    REPLAN = "replan"
    BLOCKED = "blocked"
    COMPLETE = "complete"
    WAIT_FOR_USER = "wait_for_user"
    REFUSE = "refuse"
    STOP = "stop"


ALIASES = {
    "completed": AdaptiveReplanState.COMPLETE,
    "success": AdaptiveReplanState.COMPLETE,
    "succeeded": AdaptiveReplanState.COMPLETE,
    "request_replan": AdaptiveReplanState.REPLAN,
    "retry_with_replan": AdaptiveReplanState.REPLAN,
    "block": AdaptiveReplanState.BLOCKED,
    "stop_with_root_cause": AdaptiveReplanState.BLOCKED,
    "waiting": AdaptiveReplanState.WAIT_FOR_USER,
    "wait": AdaptiveReplanState.WAIT_FOR_USER,
    "request_user_review": AdaptiveReplanState.WAIT_FOR_USER,
    "halt": AdaptiveReplanState.STOP,
    "no_action": AdaptiveReplanState.STOP,
}


def clean_adaptive_replan_state(value: AdaptiveReplanState | str | Any) -> str:
    raw = value.value if isinstance(value, AdaptiveReplanState) else str(value or "").strip().lower()
    if raw in ALIASES:
        return ALIASES[raw].value
    try:
        return AdaptiveReplanState(raw).value
    except ValueError as exc:
        raise ValueError("adaptive_replan_requires_valid_state") from exc


__all__ = ["AdaptiveReplanState", "clean_adaptive_replan_state"]
