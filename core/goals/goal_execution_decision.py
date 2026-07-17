from __future__ import annotations

"""Contracts produced by the passive goal execution planner."""

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.goals.goal_contract import clean_optional_text, clean_required_text, copy_evidence_refs


GOAL_EXECUTION_ACTIONS = frozenset(
    {"create_task", "resume_task", "wait_blocked", "complete_goal", "fail_goal", "require_review"}
)


@dataclass(frozen=True)
class GoalExecutionPlanDecision:
    action: str
    goal_id: str
    subgoal_id: str | None
    reason: str
    planner_context: Mapping[str, Any] | None = None
    resume_point: Any = None
    evidence_refs: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        action = str(self.action or "").strip()
        if action not in GOAL_EXECUTION_ACTIONS:
            raise ValueError("goal_execution_requires_valid_action")
        planner_context = self.planner_context
        if planner_context is not None and not isinstance(planner_context, Mapping):
            raise TypeError("planner_context must be a mapping or None")
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "goal_id", clean_required_text(self.goal_id, "goal_id"))
        object.__setattr__(self, "subgoal_id", clean_optional_text(self.subgoal_id))
        object.__setattr__(self, "reason", clean_required_text(self.reason, "reason"))
        object.__setattr__(self, "planner_context", copy.deepcopy(dict(planner_context or {})))
        object.__setattr__(self, "resume_point", copy.deepcopy(self.resume_point))
        object.__setattr__(self, "evidence_refs", copy_evidence_refs(self.evidence_refs))

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "goal_id": self.goal_id,
            "subgoal_id": self.subgoal_id,
            "reason": self.reason,
            "planner_context": copy.deepcopy(dict(self.planner_context or {})),
            "resume_point": copy.deepcopy(self.resume_point),
            "evidence_refs": copy.deepcopy(self.evidence_refs),
        }


__all__ = ["GOAL_EXECUTION_ACTIONS", "GoalExecutionPlanDecision"]
