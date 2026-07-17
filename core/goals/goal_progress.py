from __future__ import annotations

"""Progress and resume-point records with no execution behavior."""

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.goals.goal_contract import (
    GOAL_SCHEMA,
    clean_optional_text,
    clean_required_text,
    copy_evidence_refs,
    copy_text_list,
)
from core.goals.persistent_goal import utc_now


@dataclass(frozen=True)
class GoalResumePoint:
    goal_id: str
    subgoal_id: str | None = None
    task_id: str | None = None
    step_id: str | None = None
    reason: str | None = None
    evidence_refs: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "goal_id", clean_required_text(self.goal_id, "goal_id"))
        object.__setattr__(self, "subgoal_id", clean_optional_text(self.subgoal_id))
        object.__setattr__(self, "task_id", clean_optional_text(self.task_id))
        object.__setattr__(self, "step_id", clean_optional_text(self.step_id))
        object.__setattr__(self, "reason", clean_optional_text(self.reason))
        object.__setattr__(self, "evidence_refs", copy_evidence_refs(self.evidence_refs))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GoalResumePoint":
        return cls(
            goal_id=value.get("goal_id"),
            subgoal_id=value.get("subgoal_id"),
            task_id=value.get("task_id"),
            step_id=value.get("step_id"),
            reason=value.get("reason"),
            evidence_refs=value.get("evidence_refs") or [],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": GOAL_SCHEMA,
            "record_type": "resume_point",
            "goal_id": self.goal_id,
            "subgoal_id": self.subgoal_id,
            "task_id": self.task_id,
            "step_id": self.step_id,
            "reason": self.reason,
            "evidence_refs": copy.deepcopy(self.evidence_refs),
        }


@dataclass(frozen=True)
class GoalProgress:
    goal_id: str
    completed_subgoals: list[str] = field(default_factory=list)
    active_subgoal_id: str | None = None
    blocked_subgoals: list[str] = field(default_factory=list)
    progress_ratio: float = 0.0
    resume_point: GoalResumePoint | Mapping[str, Any] | None = None
    updated_at: str = field(default_factory=utc_now)
    evidence_refs: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        ratio = float(self.progress_ratio)
        if not 0.0 <= ratio <= 1.0:
            raise ValueError("goal_progress_ratio_must_be_between_zero_and_one")
        resume_point = self.resume_point
        if isinstance(resume_point, Mapping):
            resume_point = GoalResumePoint.from_mapping(resume_point)
        elif resume_point is not None and not isinstance(resume_point, GoalResumePoint):
            raise TypeError("resume_point must be GoalResumePoint, mapping, or None")
        object.__setattr__(self, "goal_id", clean_required_text(self.goal_id, "goal_id"))
        object.__setattr__(self, "completed_subgoals", copy_text_list(self.completed_subgoals, "completed_subgoals"))
        object.__setattr__(self, "active_subgoal_id", clean_optional_text(self.active_subgoal_id))
        object.__setattr__(self, "blocked_subgoals", copy_text_list(self.blocked_subgoals, "blocked_subgoals"))
        object.__setattr__(self, "progress_ratio", ratio)
        object.__setattr__(self, "resume_point", resume_point)
        object.__setattr__(self, "updated_at", clean_required_text(self.updated_at, "updated_at"))
        object.__setattr__(self, "evidence_refs", copy_evidence_refs(self.evidence_refs))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GoalProgress":
        return cls(
            goal_id=value.get("goal_id"),
            completed_subgoals=value.get("completed_subgoals") or [],
            active_subgoal_id=value.get("active_subgoal_id"),
            blocked_subgoals=value.get("blocked_subgoals") or [],
            progress_ratio=value.get("progress_ratio") or 0.0,
            resume_point=value.get("resume_point"),
            updated_at=value.get("updated_at") or utc_now(),
            evidence_refs=value.get("evidence_refs") or [],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": GOAL_SCHEMA,
            "record_type": "progress",
            "goal_id": self.goal_id,
            "completed_subgoals": list(self.completed_subgoals),
            "active_subgoal_id": self.active_subgoal_id,
            "blocked_subgoals": list(self.blocked_subgoals),
            "progress_ratio": self.progress_ratio,
            "resume_point": self.resume_point.to_dict() if self.resume_point is not None else None,
            "updated_at": self.updated_at,
            "evidence_refs": copy.deepcopy(self.evidence_refs),
        }


__all__ = ["GoalProgress", "GoalResumePoint"]
