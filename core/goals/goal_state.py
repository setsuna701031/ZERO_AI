from __future__ import annotations

"""Canonical lifecycle states owned by the goal state machine."""

from enum import Enum


class GoalState(str, Enum):
    CREATED = "created"
    PLANNED = "planned"
    PENDING = "pending"
    ACTIVE = "active"
    BLOCKED = "blocked"
    RESUMABLE = "resumable"
    COMPLETED = "completed"
    FAILED = "failed"


class SubgoalState(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    BLOCKED = "blocked"
    RESUMABLE = "resumable"
    COMPLETED = "completed"
    FAILED = "failed"


class TransitionAction(str, Enum):
    CREATE = "create"
    PLAN = "plan"
    START = "start"
    BLOCK = "block"
    RESUME_READY = "resume_ready"
    COMPLETE = "complete"
    FAIL = "fail"
    PAUSE = "pause"
    RETRY = "retry"


TERMINAL_GOAL_STATES = frozenset({GoalState.COMPLETED.value, GoalState.FAILED.value})
TERMINAL_SUBGOAL_STATES = frozenset({SubgoalState.COMPLETED.value, SubgoalState.FAILED.value})


def clean_target_type(value: str) -> str:
    target_type = str(value or "").strip().lower()
    if target_type not in {"goal", "subgoal"}:
        raise ValueError("goal_transition_requires_valid_target_type")
    return target_type


def clean_lifecycle_state(target_type: str, value: GoalState | SubgoalState | str) -> str:
    raw = value.value if isinstance(value, (GoalState, SubgoalState)) else str(value or "").strip().lower()
    state_type = GoalState if clean_target_type(target_type) == "goal" else SubgoalState
    try:
        return state_type(raw).value
    except ValueError as exc:
        raise ValueError(f"{target_type}_transition_requires_valid_state") from exc


def clean_transition_action(value: TransitionAction | str) -> str:
    raw = value.value if isinstance(value, TransitionAction) else str(value or "").strip().lower()
    try:
        return TransitionAction(raw).value
    except ValueError as exc:
        raise ValueError("goal_transition_requires_valid_action") from exc


__all__ = [
    "GoalState",
    "SubgoalState",
    "TERMINAL_GOAL_STATES",
    "TERMINAL_SUBGOAL_STATES",
    "TransitionAction",
    "clean_lifecycle_state",
    "clean_target_type",
    "clean_transition_action",
]
