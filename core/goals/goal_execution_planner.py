from __future__ import annotations

"""Convert orchestration decisions into passive goal execution plans."""

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from core.goals.goal_contract import clean_optional_text, clean_required_text, copy_evidence_refs
from core.goals.goal_execution_context import GoalExecutionContext
from core.goals.goal_execution_decision import GoalExecutionPlanDecision
from core.goals.goal_execution_policy import GoalExecutionPolicy
from core.goals.goal_orchestrator import GoalOrchestrationDecision
from core.goals.persistent_goal import utc_now


@dataclass(frozen=True)
class GoalExecutionPlan:
    goal_id: str
    subgoal_id: str | None
    action: str
    title: str
    description: str
    resume_point: Any
    planner_context: Mapping[str, Any]
    requires_user_review: bool
    evidence_refs: list[Any] = field(default_factory=list)
    generated_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "goal_id", clean_required_text(self.goal_id, "goal_id"))
        object.__setattr__(self, "subgoal_id", clean_optional_text(self.subgoal_id))
        object.__setattr__(self, "action", clean_required_text(self.action, "action"))
        object.__setattr__(self, "title", clean_required_text(self.title, "title"))
        object.__setattr__(self, "description", str(self.description or "").strip())
        object.__setattr__(self, "resume_point", copy.deepcopy(self.resume_point))
        object.__setattr__(self, "planner_context", copy.deepcopy(dict(self.planner_context)))
        object.__setattr__(self, "requires_user_review", bool(self.requires_user_review))
        object.__setattr__(self, "evidence_refs", copy_evidence_refs(self.evidence_refs))
        object.__setattr__(self, "generated_at", clean_required_text(self.generated_at, "generated_at"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "subgoal_id": self.subgoal_id,
            "action": self.action,
            "title": self.title,
            "description": self.description,
            "resume_point": copy.deepcopy(self.resume_point),
            "planner_context": copy.deepcopy(dict(self.planner_context)),
            "requires_user_review": self.requires_user_review,
            "evidence_refs": copy.deepcopy(self.evidence_refs),
            "generated_at": self.generated_at,
        }


class GoalExecutionPlanner:
    """Pure decision planner; it never creates tasks or invokes execution systems."""

    def __init__(self, *, policy: GoalExecutionPolicy | None = None) -> None:
        self.policy = policy or GoalExecutionPolicy()

    def decide(
        self,
        orchestration_decision: GoalOrchestrationDecision,
        *,
        execution_context: GoalExecutionContext | Mapping[str, Any] | None = None,
    ) -> GoalExecutionPlanDecision:
        context = self._planner_context(orchestration_decision, execution_context)
        action = orchestration_decision.action
        review_required = orchestration_decision.requires_user_review
        if action in {"start_subgoal", "continue"}:
            if (
                review_required
                or not self.policy.allow_create_task_from_subgoal
                or self.policy.require_review_before_create_task
            ):
                mapped_action = "require_review"
                reason = f"{action}_requires_review"
            else:
                mapped_action = "create_task"
                reason = f"{action}_ready_for_task_planning"
        elif action == "resume_subgoal":
            if (
                review_required
                or orchestration_decision.resume_point is None
                or not self.policy.allow_resume_task_from_resume_point
                or self.policy.require_review_before_resume
            ):
                mapped_action = "require_review"
                reason = "resume_subgoal_requires_review"
            else:
                mapped_action = "resume_task"
                reason = "resume_point_ready_for_task_planning"
        elif action == "wait_blocked":
            mapped_action = "wait_blocked"
            reason = orchestration_decision.reason
        elif action == "complete_goal":
            if review_required or self.policy.require_review_before_complete_goal:
                mapped_action = "require_review"
                reason = "complete_goal_requires_review"
            else:
                mapped_action = "complete_goal"
                reason = "complete_goal_ready_for_reviewed_transition"
        else:
            mapped_action = "require_review" if review_required else "fail_goal"
            reason = "fail_goal_requires_review" if review_required else orchestration_decision.reason
        return GoalExecutionPlanDecision(
            action=mapped_action,
            goal_id=orchestration_decision.goal_id,
            subgoal_id=orchestration_decision.subgoal_id,
            reason=reason,
            planner_context=context,
            resume_point=orchestration_decision.resume_point,
            evidence_refs=orchestration_decision.evidence_refs,
        )

    def plan(
        self,
        orchestration_decision: GoalOrchestrationDecision,
        *,
        execution_context: GoalExecutionContext | Mapping[str, Any] | None = None,
    ) -> GoalExecutionPlan:
        decision = self.decide(orchestration_decision, execution_context=execution_context)
        context = decision.planner_context or {}
        title = str(context.get("title") or orchestration_decision.subgoal_id or orchestration_decision.goal_id)
        return GoalExecutionPlan(
            goal_id=decision.goal_id,
            subgoal_id=decision.subgoal_id,
            action=decision.action,
            title=title,
            description=str(context.get("description") or ""),
            resume_point=decision.resume_point,
            planner_context=context,
            requires_user_review=decision.action == "require_review",
            evidence_refs=decision.evidence_refs,
        )

    def plan_many(
        self,
        items: Sequence[
            tuple[GoalOrchestrationDecision, GoalExecutionContext | Mapping[str, Any] | None]
            | GoalOrchestrationDecision
        ],
    ) -> list[GoalExecutionPlan]:
        plans: list[GoalExecutionPlan] = []
        for item in items[: self.policy.max_execution_plans_per_cycle]:
            if isinstance(item, tuple):
                orchestration_decision, execution_context = item
            else:
                orchestration_decision, execution_context = item, None
            plans.append(self.plan(orchestration_decision, execution_context=execution_context))
        return plans

    @staticmethod
    def _planner_context(
        orchestration_decision: GoalOrchestrationDecision,
        execution_context: GoalExecutionContext | Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if isinstance(execution_context, GoalExecutionContext):
            context = execution_context.to_dict()
        elif isinstance(execution_context, Mapping):
            context = copy.deepcopy(dict(execution_context))
        elif execution_context is None:
            context = {}
        else:
            raise TypeError("execution_context must be GoalExecutionContext, mapping, or None")
        context["goal_id"] = orchestration_decision.goal_id
        context["subgoal_id"] = orchestration_decision.subgoal_id
        context["orchestration_action"] = orchestration_decision.action
        context["orchestration_reason"] = orchestration_decision.reason
        context["resume_point"] = copy.deepcopy(orchestration_decision.resume_point)
        context["evidence_refs"] = copy.deepcopy(orchestration_decision.evidence_refs)
        return context


__all__ = ["GoalExecutionPlan", "GoalExecutionPlanner"]
