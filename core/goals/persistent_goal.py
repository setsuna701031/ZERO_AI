from __future__ import annotations

"""Passive goal and subgoal persistence records."""

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from core.goals.goal_contract import (
    GOAL_SCHEMA,
    GoalStatus,
    clean_optional_text,
    clean_required_text,
    clean_status,
    copy_evidence_refs,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PersistentGoal:
    goal_id: str
    title: str
    description: str = ""
    status: GoalStatus | str = GoalStatus.PENDING
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    evidence_refs: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "goal_id", clean_required_text(self.goal_id, "goal_id"))
        object.__setattr__(self, "title", clean_required_text(self.title, "title"))
        object.__setattr__(self, "description", str(self.description or "").strip())
        object.__setattr__(self, "status", clean_status(self.status))
        object.__setattr__(self, "created_at", clean_required_text(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", clean_required_text(self.updated_at, "updated_at"))
        object.__setattr__(self, "evidence_refs", copy_evidence_refs(self.evidence_refs))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PersistentGoal":
        return cls(
            goal_id=value.get("goal_id"),
            title=value.get("title"),
            description=value.get("description") or "",
            status=value.get("status") or GoalStatus.PENDING,
            created_at=value.get("created_at") or utc_now(),
            updated_at=value.get("updated_at") or value.get("created_at") or utc_now(),
            evidence_refs=value.get("evidence_refs") or [],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": GOAL_SCHEMA,
            "record_type": "goal",
            "goal_id": self.goal_id,
            "title": self.title,
            "description": self.description,
            "status": str(self.status),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "evidence_refs": copy.deepcopy(self.evidence_refs),
        }


@dataclass(frozen=True)
class PersistentSubgoal:
    subgoal_id: str
    goal_id: str
    title: str
    status: GoalStatus | str = GoalStatus.PENDING
    order: int = 0
    progress: float = 0.0
    blocked_reason: str | None = None
    resume_point: Any = None
    evidence_refs: list[Any] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        progress = float(self.progress)
        if not 0.0 <= progress <= 1.0:
            raise ValueError("subgoal_progress_must_be_between_zero_and_one")
        resume_point = self.resume_point
        if resume_point is not None and hasattr(resume_point, "to_dict"):
            resume_point = resume_point.to_dict()
        object.__setattr__(self, "subgoal_id", clean_required_text(self.subgoal_id, "subgoal_id"))
        object.__setattr__(self, "goal_id", clean_required_text(self.goal_id, "goal_id"))
        object.__setattr__(self, "title", clean_required_text(self.title, "title"))
        object.__setattr__(self, "status", clean_status(self.status))
        object.__setattr__(self, "order", int(self.order))
        object.__setattr__(self, "progress", progress)
        object.__setattr__(self, "blocked_reason", clean_optional_text(self.blocked_reason))
        object.__setattr__(self, "resume_point", copy.deepcopy(resume_point))
        object.__setattr__(self, "evidence_refs", copy_evidence_refs(self.evidence_refs))
        object.__setattr__(self, "created_at", clean_required_text(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", clean_required_text(self.updated_at, "updated_at"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PersistentSubgoal":
        return cls(
            subgoal_id=value.get("subgoal_id"),
            goal_id=value.get("goal_id"),
            title=value.get("title"),
            status=value.get("status") or GoalStatus.PENDING,
            order=value.get("order") or 0,
            progress=value.get("progress") or 0.0,
            blocked_reason=value.get("blocked_reason"),
            resume_point=value.get("resume_point"),
            evidence_refs=value.get("evidence_refs") or [],
            created_at=value.get("created_at") or utc_now(),
            updated_at=value.get("updated_at") or value.get("created_at") or utc_now(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": GOAL_SCHEMA,
            "record_type": "subgoal",
            "subgoal_id": self.subgoal_id,
            "goal_id": self.goal_id,
            "title": self.title,
            "status": str(self.status),
            "order": self.order,
            "progress": self.progress,
            "blocked_reason": self.blocked_reason,
            "resume_point": copy.deepcopy(self.resume_point),
            "evidence_refs": copy.deepcopy(self.evidence_refs),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


__all__ = ["PersistentGoal", "PersistentSubgoal", "utc_now"]
