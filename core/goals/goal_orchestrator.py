from __future__ import annotations

"""Read-only goal orchestration that produces context and decisions only."""

import copy
from dataclasses import dataclass, field
from typing import Any

from core.goals.goal_contract import clean_optional_text, clean_required_text, copy_evidence_refs
from core.goals.goal_execution_context import GoalExecutionContext
from core.goals.goal_lifecycle_policy import GoalLifecyclePolicy
from core.goals.goal_repository import GoalRepository


GOAL_ORCHESTRATION_ACTIONS = frozenset(
    {"continue", "start_subgoal", "resume_subgoal", "wait_blocked", "complete_goal", "fail_goal"}
)


@dataclass(frozen=True)
class GoalOrchestrationDecision:
    action: str
    goal_id: str
    subgoal_id: str | None = None
    reason: str = ""
    resume_point: Any = None
    requires_user_review: bool = False
    evidence_refs: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        action = str(self.action or "").strip()
        if action not in GOAL_ORCHESTRATION_ACTIONS:
            raise ValueError("goal_orchestration_requires_valid_action")
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "goal_id", clean_required_text(self.goal_id, "goal_id"))
        object.__setattr__(self, "subgoal_id", clean_optional_text(self.subgoal_id))
        object.__setattr__(self, "reason", clean_required_text(self.reason, "reason"))
        object.__setattr__(self, "resume_point", copy.deepcopy(self.resume_point))
        object.__setattr__(self, "requires_user_review", bool(self.requires_user_review))
        object.__setattr__(self, "evidence_refs", copy_evidence_refs(self.evidence_refs))

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "goal_id": self.goal_id,
            "subgoal_id": self.subgoal_id,
            "reason": self.reason,
            "resume_point": copy.deepcopy(self.resume_point),
            "requires_user_review": self.requires_user_review,
            "evidence_refs": copy.deepcopy(self.evidence_refs),
        }


class GoalOrchestrator:
    """Inspect goal state and return one passive orchestration decision."""

    def __init__(
        self,
        repository: GoalRepository | None = None,
        *,
        policy: GoalLifecyclePolicy | None = None,
    ) -> None:
        self.repository = repository
        self.policy = policy or GoalLifecyclePolicy()

    def build_execution_context(
        self,
        goal_id: str,
        *,
        subgoal_id: str | None = None,
        related_memory_context: Any = None,
    ) -> GoalExecutionContext | None:
        if self.repository is None:
            return None
        snapshot = self.repository.get_orchestration_snapshot(goal_id)
        goal = snapshot["goal"]
        if goal is None:
            return None
        selected = self._select_context_subgoal(snapshot["subgoals"], snapshot["progress"], subgoal_id)
        if selected is None:
            return GoalExecutionContext(
                goal_id=goal["goal_id"],
                subgoal_id=None,
                title=goal["title"],
                description=goal.get("description") or "",
                status=goal["status"],
                resume_point=snapshot["resume_point"],
                related_memory_context=related_memory_context,
                evidence_refs=goal.get("evidence_refs") or [],
            )
        return GoalExecutionContext(
            goal_id=goal["goal_id"],
            subgoal_id=selected["subgoal_id"],
            title=selected["title"],
            description=goal.get("description") or "",
            status=selected["status"],
            resume_point=selected.get("resume_point") or snapshot["resume_point"],
            related_memory_context=related_memory_context,
            evidence_refs=self._union(goal.get("evidence_refs"), selected.get("evidence_refs")),
        )

    def build_execution_contexts(
        self,
        goal_id: str,
        *,
        related_memory_context: Any = None,
    ) -> list[GoalExecutionContext]:
        if self.repository is None:
            return []
        snapshot = self.repository.get_orchestration_snapshot(goal_id)
        if snapshot["goal"] is None:
            return []
        active = self._active_subgoal(snapshot["subgoals"], snapshot["progress"])
        if active is not None:
            selected_ids = [active["subgoal_id"]]
        else:
            selected_ids = [
                item["subgoal_id"]
                for item in snapshot["subgoals"]
                if item["status"] in {"blocked", "pending"}
            ][: self.policy.max_subgoals_per_cycle]
        if not selected_ids:
            context = self.build_execution_context(goal_id, related_memory_context=related_memory_context)
            return [context] if context is not None else []
        contexts: list[GoalExecutionContext] = []
        for subgoal_id in selected_ids:
            context = self.build_execution_context(
                goal_id,
                subgoal_id=subgoal_id,
                related_memory_context=related_memory_context,
            )
            if context is not None:
                contexts.append(context)
        return contexts

    def decide(self, goal_id: str, *, contract_violation: str | None = None) -> GoalOrchestrationDecision:
        target = clean_required_text(goal_id, "goal_id")
        if self.repository is None:
            return self._decision("wait_blocked", target, "goal_repository_unavailable", review=True)
        snapshot = self.repository.get_orchestration_snapshot(target)
        goal = snapshot["goal"]
        if goal is None:
            return self._decision("fail_goal", target, "goal_not_found", review=True)
        evidence_refs = goal.get("evidence_refs") or []
        if contract_violation:
            return self._decision(
                "wait_blocked",
                target,
                f"contract_violation:{str(contract_violation).strip()}",
                review=True,
                evidence_refs=evidence_refs,
            )
        if goal["status"] == "failed":
            return self._decision("fail_goal", target, "goal_status_failed", review=True, evidence_refs=evidence_refs)
        if goal["status"] == "completed":
            return self._decision(
                "complete_goal",
                target,
                "goal_already_completed",
                review=self.policy.require_review_before_goal_completion,
                evidence_refs=evidence_refs,
            )

        subgoals = snapshot["subgoals"]
        active = self._active_subgoal(subgoals, snapshot["progress"])
        if active is not None:
            return self._decide_for_active(goal, active, snapshot["resume_point"])

        blocked = next((item for item in subgoals if item["status"] == "blocked"), None)
        if blocked is not None:
            return self._decide_for_blocked(goal, blocked, blocked.get("resume_point") or snapshot["resume_point"])

        pending = [item for item in subgoals if item["status"] == "pending"]
        if pending:
            selected = pending[: self.policy.max_subgoals_per_cycle][0]
            return self._decision(
                "start_subgoal",
                target,
                "first_pending_subgoal",
                subgoal_id=selected["subgoal_id"],
                review=not self.policy.allow_auto_start_next_subgoal,
                evidence_refs=self._union(evidence_refs, selected.get("evidence_refs")),
            )

        if subgoals and all(item["status"] == "completed" for item in subgoals):
            return self._decision(
                "complete_goal",
                target,
                "all_subgoals_completed",
                review=self.policy.require_review_before_goal_completion,
                evidence_refs=evidence_refs,
            )
        return self._decision("wait_blocked", target, "no_actionable_subgoal", review=True, evidence_refs=evidence_refs)

    def _decide_for_active(
        self,
        goal: dict[str, Any],
        subgoal: dict[str, Any],
        resume_point: Any,
    ) -> GoalOrchestrationDecision:
        if subgoal["status"] == "blocked":
            return self._decide_for_blocked(goal, subgoal, subgoal.get("resume_point") or resume_point)
        return self._decision(
            "continue",
            goal["goal_id"],
            "active_subgoal",
            subgoal_id=subgoal["subgoal_id"],
            evidence_refs=self._union(goal.get("evidence_refs"), subgoal.get("evidence_refs")),
        )

    def _decide_for_blocked(
        self,
        goal: dict[str, Any],
        subgoal: dict[str, Any],
        resume_point: Any,
    ) -> GoalOrchestrationDecision:
        evidence_refs = self._union(goal.get("evidence_refs"), subgoal.get("evidence_refs"))
        if resume_point is not None and self.policy.allow_resume_blocked_subgoal:
            return self._decision(
                "resume_subgoal",
                goal["goal_id"],
                "blocked_subgoal_has_resume_point",
                subgoal_id=subgoal["subgoal_id"],
                resume_point=resume_point,
                review=self.policy.require_review_before_resume,
                evidence_refs=evidence_refs,
            )
        return self._decision(
            "wait_blocked",
            goal["goal_id"],
            subgoal.get("blocked_reason") or "blocked_subgoal_requires_review",
            subgoal_id=subgoal["subgoal_id"],
            resume_point=resume_point,
            review=True,
            evidence_refs=evidence_refs,
        )

    @staticmethod
    def _active_subgoal(subgoals: list[dict[str, Any]], progress: dict[str, Any] | None) -> dict[str, Any] | None:
        active_id = progress.get("active_subgoal_id") if progress else None
        if active_id:
            selected = next((item for item in subgoals if item["subgoal_id"] == active_id), None)
            if selected is not None and selected["status"] in {"active", "blocked"}:
                return selected
        return next((item for item in subgoals if item["status"] == "active"), None)

    def _select_context_subgoal(
        self,
        subgoals: list[dict[str, Any]],
        progress: dict[str, Any] | None,
        subgoal_id: str | None,
    ) -> dict[str, Any] | None:
        if subgoal_id is not None:
            return next((item for item in subgoals if item["subgoal_id"] == subgoal_id), None)
        active = self._active_subgoal(subgoals, progress)
        if active is not None:
            return active
        actionable = [item for item in subgoals if item["status"] in {"blocked", "pending"}]
        return actionable[: self.policy.max_subgoals_per_cycle][0] if actionable else None

    @staticmethod
    def _decision(
        action: str,
        goal_id: str,
        reason: str,
        *,
        subgoal_id: str | None = None,
        resume_point: Any = None,
        review: bool = False,
        evidence_refs: Any = None,
    ) -> GoalOrchestrationDecision:
        return GoalOrchestrationDecision(
            action=action,
            goal_id=goal_id,
            subgoal_id=subgoal_id,
            reason=reason,
            resume_point=resume_point,
            requires_user_review=review,
            evidence_refs=evidence_refs or [],
        )

    @staticmethod
    def _union(first: Any, second: Any) -> list[Any]:
        result: list[Any] = []
        for value in list(first or []) + list(second or []):
            if value not in result:
                result.append(copy.deepcopy(value))
        return result


__all__ = ["GOAL_ORCHESTRATION_ACTIONS", "GoalOrchestrationDecision", "GoalOrchestrator"]
