from __future__ import annotations

"""Validated execution request delivered after adaptive planning is complete."""

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.adaptive.adaptive_decision import clean_adaptive_decision_type
from core.goals.goal_contract import clean_optional_text, clean_required_text, copy_evidence_refs


ADAPTIVE_ACTION_TYPES = frozenset(
    {
        "execute_next_step",
        "mark_blocked_request",
        "no_action",
        "wait_for_user",
    }
)


@dataclass(frozen=True)
class AdaptiveExecutionContract:
    plan_id: str
    goal_id: str
    subgoal_id: str | None
    decision_type: str
    action_type: str
    reason: str
    requires_user_review: bool = False
    evidence_required: list[Any] = field(default_factory=list)
    runtime_allowed: bool = False
    blocked_reason: str | None = None

    def __post_init__(self) -> None:
        action_type = str(self.action_type or "").strip().lower()
        if action_type not in ADAPTIVE_ACTION_TYPES:
            raise ValueError("adaptive_execution_contract_requires_valid_action_type")
        object.__setattr__(self, "plan_id", clean_required_text(self.plan_id, "adaptive_plan_id"))
        object.__setattr__(self, "goal_id", clean_required_text(self.goal_id, "goal_id"))
        object.__setattr__(self, "subgoal_id", clean_optional_text(self.subgoal_id))
        object.__setattr__(self, "decision_type", clean_adaptive_decision_type(self.decision_type))
        object.__setattr__(self, "action_type", action_type)
        object.__setattr__(self, "reason", clean_required_text(self.reason, "adaptive_execution_reason"))
        object.__setattr__(self, "requires_user_review", bool(self.requires_user_review))
        object.__setattr__(self, "evidence_required", copy_evidence_refs(self.evidence_required))
        object.__setattr__(self, "runtime_allowed", bool(self.runtime_allowed))
        object.__setattr__(self, "blocked_reason", clean_optional_text(self.blocked_reason))
        if self.decision_type == "request_evidence":
            raise ValueError("request_evidence_requires_evidence_contract")
        if self.requires_user_review and self.runtime_allowed:
            raise ValueError("adaptive_execution_review_cannot_allow_runtime")
        if not self.runtime_allowed and self.action_type == "execute_next_step":
            raise ValueError("adaptive_execution_disallowed_runtime_cannot_execute")
        expected_action = {
            "continue_active": "execute_next_step",
            "resume_blocked": "execute_next_step",
            "wait_for_user": "wait_for_user",
            "no_action": "no_action",
            "mark_blocked": "mark_blocked_request",
        }.get(self.decision_type)
        if expected_action is not None and not self.requires_user_review and self.action_type != expected_action:
            raise ValueError("adaptive_execution_action_does_not_match_decision")
        if self.action_type != "execute_next_step" and self.runtime_allowed:
            raise ValueError("adaptive_execution_non_execution_action_cannot_allow_runtime")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AdaptiveExecutionContract":
        return cls(
            plan_id=value.get("plan_id"),
            goal_id=value.get("goal_id"),
            subgoal_id=value.get("subgoal_id"),
            decision_type=value.get("decision_type"),
            action_type=value.get("action_type"),
            reason=value.get("reason"),
            requires_user_review=value.get("requires_user_review", False),
            evidence_required=value.get("evidence_required") or [],
            runtime_allowed=value.get("runtime_allowed", False),
            blocked_reason=value.get("blocked_reason"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal_id": self.goal_id,
            "subgoal_id": self.subgoal_id,
            "decision_type": self.decision_type,
            "action_type": self.action_type,
            "reason": self.reason,
            "requires_user_review": self.requires_user_review,
            "evidence_required": copy.deepcopy(self.evidence_required),
            "runtime_allowed": self.runtime_allowed,
            "blocked_reason": self.blocked_reason,
        }


__all__ = ["ADAPTIVE_ACTION_TYPES", "AdaptiveExecutionContract"]
