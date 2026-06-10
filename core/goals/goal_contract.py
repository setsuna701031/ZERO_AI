from __future__ import annotations

"""Contracts shared by the persistent goal progress layer."""

import copy
from enum import Enum
from typing import Any


GOAL_SCHEMA = "zero.persistent_goal.v1"
GOAL_EVENT_SCHEMA = "zero.persistent_goal_event.v1"


class GoalStatus(str, Enum):
    CREATED = "created"
    PLANNED = "planned"
    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    BLOCKED = "blocked"
    RESUMABLE = "resumable"
    COMPLETED = "completed"
    FAILED = "failed"


TERMINAL_GOAL_STATUSES = frozenset({GoalStatus.COMPLETED.value, GoalStatus.FAILED.value})


def clean_required_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"goal_requires_{field_name}")
    return text


def clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def clean_status(value: GoalStatus | str) -> str:
    raw = value.value if isinstance(value, GoalStatus) else str(value or "").strip().lower()
    try:
        return GoalStatus(raw).value
    except ValueError as exc:
        raise ValueError("goal_requires_valid_status") from exc


def copy_evidence_refs(value: Any) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise TypeError("evidence_refs must be a list or tuple")
    return copy.deepcopy(list(value))


def copy_text_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{field_name} must be a list or tuple")
    result: list[str] = []
    for item in value:
        text = clean_required_text(item, field_name)
        if text not in result:
            result.append(text)
    return result


__all__ = [
    "GOAL_EVENT_SCHEMA",
    "GOAL_SCHEMA",
    "GoalStatus",
    "TERMINAL_GOAL_STATUSES",
    "clean_optional_text",
    "clean_required_text",
    "clean_status",
    "copy_evidence_refs",
    "copy_text_list",
]
