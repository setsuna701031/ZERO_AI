from __future__ import annotations

"""Decision vocabulary for goal-aware adaptive planning."""

from enum import Enum


class AdaptiveDecisionType(str, Enum):
    CONTINUE_ACTIVE = "continue_active"
    RESUME_BLOCKED = "resume_blocked"
    REQUEST_EVIDENCE = "request_evidence"
    MARK_BLOCKED = "mark_blocked"
    WAIT_FOR_USER = "wait_for_user"
    NO_ACTION = "no_action"


def clean_adaptive_decision_type(value: AdaptiveDecisionType | str) -> str:
    raw = value.value if isinstance(value, AdaptiveDecisionType) else str(value or "").strip().lower()
    try:
        return AdaptiveDecisionType(raw).value
    except ValueError as exc:
        raise ValueError("adaptive_plan_requires_valid_decision_type") from exc


AdaptivePlanningDecision = AdaptiveDecisionType


__all__ = ["AdaptiveDecisionType", "AdaptivePlanningDecision", "clean_adaptive_decision_type"]
