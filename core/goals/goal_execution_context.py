from __future__ import annotations

"""Planner-facing context produced from persistent goal records."""

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.goals.goal_contract import clean_optional_text, clean_required_text, copy_evidence_refs
from core.goals.persistent_goal import utc_now


@dataclass(frozen=True)
class GoalExecutionContext:
    goal_id: str
    subgoal_id: str | None
    title: str
    description: str
    status: str
    resume_point: Any = None
    related_memory_context: Any = None
    evidence_refs: list[Any] = field(default_factory=list)
    generated_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "goal_id", clean_required_text(self.goal_id, "goal_id"))
        object.__setattr__(self, "subgoal_id", clean_optional_text(self.subgoal_id))
        object.__setattr__(self, "title", clean_required_text(self.title, "title"))
        object.__setattr__(self, "description", str(self.description or "").strip())
        object.__setattr__(self, "status", clean_required_text(self.status, "status"))
        object.__setattr__(self, "resume_point", copy.deepcopy(self.resume_point))
        object.__setattr__(self, "related_memory_context", copy.deepcopy(self.related_memory_context))
        object.__setattr__(self, "evidence_refs", copy_evidence_refs(self.evidence_refs))
        object.__setattr__(self, "generated_at", clean_required_text(self.generated_at, "generated_at"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GoalExecutionContext":
        return cls(
            goal_id=value.get("goal_id"),
            subgoal_id=value.get("subgoal_id"),
            title=value.get("title"),
            description=value.get("description") or "",
            status=value.get("status"),
            resume_point=value.get("resume_point"),
            related_memory_context=value.get("related_memory_context"),
            evidence_refs=value.get("evidence_refs") or [],
            generated_at=value.get("generated_at") or utc_now(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "subgoal_id": self.subgoal_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "resume_point": copy.deepcopy(self.resume_point),
            "related_memory_context": copy.deepcopy(self.related_memory_context),
            "evidence_refs": copy.deepcopy(self.evidence_refs),
            "generated_at": self.generated_at,
        }


__all__ = ["GoalExecutionContext"]
