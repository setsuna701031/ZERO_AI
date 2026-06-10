from __future__ import annotations

"""Passive transition requests and state-machine decisions."""

import copy
from dataclasses import dataclass, field
from typing import Any

from core.goals.goal_contract import clean_optional_text, clean_required_text, copy_evidence_refs
from core.goals.goal_state import clean_lifecycle_state, clean_target_type, clean_transition_action


@dataclass(frozen=True)
class GoalTransition:
    target_type: str
    target_id: str
    from_state: str
    to_state: str
    action: str
    reason: str | None = None
    resume_point: Any = None
    evidence_refs: list[Any] = field(default_factory=list)
    requires_user_review: bool = False

    def __post_init__(self) -> None:
        target_type = clean_target_type(self.target_type)
        resume_point = self.resume_point.to_dict() if hasattr(self.resume_point, "to_dict") else self.resume_point
        object.__setattr__(self, "target_type", target_type)
        object.__setattr__(self, "target_id", clean_required_text(self.target_id, "transition_target_id"))
        object.__setattr__(self, "from_state", clean_lifecycle_state(target_type, self.from_state))
        object.__setattr__(self, "to_state", clean_lifecycle_state(target_type, self.to_state))
        object.__setattr__(self, "action", clean_transition_action(self.action))
        object.__setattr__(self, "reason", clean_optional_text(self.reason))
        object.__setattr__(self, "resume_point", copy.deepcopy(resume_point))
        object.__setattr__(self, "evidence_refs", copy_evidence_refs(self.evidence_refs))
        object.__setattr__(self, "requires_user_review", bool(self.requires_user_review))


@dataclass(frozen=True)
class GoalTransitionResult:
    accepted: bool
    from_state: str
    to_state: str
    reason: str
    blocked_reason: str | None = None
    requires_user_review: bool = False
    evidence_refs: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "accepted", bool(self.accepted))
        object.__setattr__(self, "from_state", str(self.from_state))
        object.__setattr__(self, "to_state", str(self.to_state))
        object.__setattr__(self, "reason", clean_required_text(self.reason, "transition_result_reason"))
        object.__setattr__(self, "blocked_reason", clean_optional_text(self.blocked_reason))
        object.__setattr__(self, "requires_user_review", bool(self.requires_user_review))
        object.__setattr__(self, "evidence_refs", copy_evidence_refs(self.evidence_refs))


__all__ = ["GoalTransition", "GoalTransitionResult"]
