from __future__ import annotations

"""Passive output contract for AdaptivePlanner."""

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.adaptive.adaptive_decision import AdaptiveDecisionType, clean_adaptive_decision_type
from core.goals.goal_contract import clean_optional_text, clean_required_text, copy_evidence_refs


@dataclass(frozen=True)
class AdaptivePlan:
    selected_goal_id: str
    selected_subgoal_id: str | None
    decision_type: AdaptiveDecisionType | str
    reason: str
    required_transition: Mapping[str, Any] | None = None
    requires_user_review: bool = False
    evidence_required: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        transition = None if self.required_transition is None else copy.deepcopy(dict(self.required_transition))
        object.__setattr__(self, "selected_goal_id", clean_required_text(self.selected_goal_id, "selected_goal_id"))
        object.__setattr__(self, "selected_subgoal_id", clean_optional_text(self.selected_subgoal_id))
        object.__setattr__(self, "decision_type", clean_adaptive_decision_type(self.decision_type))
        object.__setattr__(self, "reason", clean_required_text(self.reason, "adaptive_plan_reason"))
        object.__setattr__(self, "required_transition", transition)
        object.__setattr__(self, "requires_user_review", bool(self.requires_user_review))
        object.__setattr__(self, "evidence_required", copy_evidence_refs(self.evidence_required))

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_goal_id": self.selected_goal_id,
            "selected_subgoal_id": self.selected_subgoal_id,
            "decision_type": self.decision_type,
            "reason": self.reason,
            "required_transition": copy.deepcopy(self.required_transition),
            "requires_user_review": self.requires_user_review,
            "evidence_required": copy.deepcopy(self.evidence_required),
        }


__all__ = ["AdaptivePlan"]
