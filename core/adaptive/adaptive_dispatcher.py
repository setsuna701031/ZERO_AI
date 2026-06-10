from __future__ import annotations

"""Convert completed adaptive plans into passive Runtime execution requests."""

import hashlib
import json
from typing import Any, Mapping

from core.adaptive.adaptive_execution_contract import AdaptiveExecutionContract
from core.adaptive.adaptive_plan import AdaptivePlan
from core.evidence.evidence_contract import EvidenceContract


class AdaptiveDispatcher:
    _ACTION_TYPES = {
        "continue_active": "execute_next_step",
        "wait_for_user": "wait_for_user",
        "no_action": "no_action",
        "resume_blocked": "execute_next_step",
        "mark_blocked": "mark_blocked_request",
    }
    _RUNTIME_ALLOWED_ACTIONS = frozenset({"execute_next_step"})

    def dispatch(
        self,
        plan: AdaptivePlan | Mapping[str, Any],
        *,
        plan_id: str | None = None,
    ) -> AdaptiveExecutionContract | EvidenceContract:
        adaptive_plan = plan if isinstance(plan, AdaptivePlan) else AdaptivePlan(**dict(plan))
        resolved_plan_id = plan_id or self._plan_id(adaptive_plan)
        if adaptive_plan.decision_type == "request_evidence":
            return EvidenceContract(
                plan_id=resolved_plan_id,
                goal_id=adaptive_plan.selected_goal_id,
                subgoal_id=adaptive_plan.selected_subgoal_id,
                reason=adaptive_plan.reason,
                evidence_required=adaptive_plan.evidence_required,
            )
        action_type = self._ACTION_TYPES[adaptive_plan.decision_type]
        runtime_allowed = action_type in self._RUNTIME_ALLOWED_ACTIONS
        blocked_reason = None

        if adaptive_plan.requires_user_review:
            action_type = "wait_for_user"
            runtime_allowed = False
            blocked_reason = "adaptive_plan_requires_user_review"
        elif adaptive_plan.decision_type == "no_action":
            runtime_allowed = False
            blocked_reason = adaptive_plan.reason
        elif adaptive_plan.decision_type == "wait_for_user":
            runtime_allowed = False
            blocked_reason = adaptive_plan.reason
        elif adaptive_plan.decision_type == "mark_blocked":
            runtime_allowed = False
            blocked_reason = adaptive_plan.reason

        return AdaptiveExecutionContract(
            plan_id=resolved_plan_id,
            goal_id=adaptive_plan.selected_goal_id,
            subgoal_id=adaptive_plan.selected_subgoal_id,
            decision_type=adaptive_plan.decision_type,
            action_type=action_type,
            reason=adaptive_plan.reason,
            requires_user_review=adaptive_plan.requires_user_review,
            evidence_required=adaptive_plan.evidence_required,
            runtime_allowed=runtime_allowed,
            blocked_reason=blocked_reason,
        )

    @staticmethod
    def _plan_id(plan: AdaptivePlan) -> str:
        encoded = json.dumps(plan.to_dict(), sort_keys=True, default=str).encode("utf-8")
        return f"adaptive-plan:{hashlib.sha256(encoded).hexdigest()[:16]}"


__all__ = ["AdaptiveDispatcher"]
