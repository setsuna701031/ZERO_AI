from __future__ import annotations

"""Goal-aware adaptive planning that returns decisions without executing them."""

import copy
from typing import Any, Mapping, Sequence

from core.adaptive.adaptive_plan import AdaptivePlan
from core.adaptive.adaptive_policy import AdaptivePolicy
from core.evidence.evidence_chain import EvidenceChain
from core.evidence.evidence_record import EvidenceRecord
from core.goals.goal_completion_authority import GoalCompletionAuthority
from core.goals.goal_state_machine import GoalStateMachine
from core.goals.goal_transition import GoalTransition, GoalTransitionResult


class AdaptivePlanner:
    def __init__(
        self,
        *,
        state_machine: GoalStateMachine | None = None,
        completion_authority: GoalCompletionAuthority | None = None,
        policy: AdaptivePolicy | None = None,
    ) -> None:
        self.state_machine = state_machine or GoalStateMachine()
        self.completion_authority = completion_authority or GoalCompletionAuthority(
            state_machine=self.state_machine
        )
        self.policy = policy or AdaptivePolicy()

    def decide(
        self,
        *,
        current_goal: Mapping[str, Any] | Any,
        subgoals: Sequence[Mapping[str, Any] | Any],
        current_state: Mapping[str, Any] | str | None = None,
        evidence_summary: EvidenceChain | Mapping[str, Any] | Sequence[Any] | None = None,
        blocker_summary: Mapping[str, Any] | Sequence[Any] | str | None = None,
    ) -> AdaptivePlan:
        goal = self._record(current_goal)
        normalized_subgoals = [self._record(item) for item in subgoals]
        goal_id = self._required_id(goal, "goal_id")
        goal_state = self._state(current_state, goal)
        evidence, rejected_count = self._evidence_status(evidence_summary, goal)
        all_completed = all(self._state(None, item) == "completed" for item in normalized_subgoals)

        if rejected_count:
            return self._plan(
                goal_id,
                None,
                "request_evidence",
                "rejected_evidence_blocks_goal_completion",
                evidence_required=["replacement_completion_evidence"],
            )

        if goal_state == "completed":
            if self.policy.require_evidence_for_completion and not evidence:
                return self._plan(
                    goal_id,
                    None,
                    "request_evidence",
                    "completed_goal_requires_evidence",
                    evidence_required=["completion_evidence"],
                )
            if self.policy.require_all_subgoals_completed and not all_completed:
                return self._plan(
                    goal_id,
                    self._first_incomplete_id(normalized_subgoals),
                    "no_action",
                    "completed_goal_has_incomplete_subgoals",
                    review=True,
                )
            return self._plan(goal_id, None, "no_action", "goal_already_completed")

        if goal_state == "active" and all_completed:
            if self.policy.require_evidence_for_completion and not evidence:
                return self._plan(
                    goal_id,
                    None,
                    "request_evidence",
                    "goal_completion_requires_validated_evidence",
                    evidence_required=["completion_evidence"],
                )

            result = self.completion_authority.complete_goal(
                goal_id=goal_id,
                from_state="active",
                evidence_refs=evidence,
                all_subgoals_completed=True,
                reason="validated_evidence_and_subgoals_ready",
            )
            if not result.accepted:
                return self._plan(
                    goal_id,
                    None,
                    "no_action",
                    result.blocked_reason or result.reason,
                    review=result.requires_user_review,
                )
            return self._plan(
                goal_id,
                None,
                "no_action",
                "goal_completion_transition_ready",
                transition=self._completion_transition_dict(goal_id, result),
                review=result.requires_user_review,
            )

        selected = self._select_subgoal(normalized_subgoals)
        if selected is None:
            return self._plan(goal_id, None, "no_action", "no_actionable_subgoal")

        subgoal_id = self._required_id(selected, "subgoal_id")
        subgoal_state = self._state(None, selected)

        if subgoal_state in {"blocked", "resumable"}:
            return self._resume_decision(goal_id, selected, subgoal_state)

        blocker_reason = self._blocker_reason(blocker_summary, selected)
        if blocker_reason:
            transition = GoalTransition(
                "subgoal",
                subgoal_id,
                subgoal_state,
                "blocked",
                "block",
                blocker_reason,
            )
            result = self.state_machine.transition(transition)
            if not result.accepted:
                return self._rejected(goal_id, subgoal_id, result)
            return self._plan(
                goal_id,
                subgoal_id,
                "mark_blocked",
                blocker_reason,
                transition=transition,
                review=result.requires_user_review,
            )

        if subgoal_state == "active":
            return self._plan(goal_id, subgoal_id, "continue_active", "active_subgoal_can_continue")

        return self._plan(goal_id, subgoal_id, "no_action", f"no_adaptive_action_for_{subgoal_state}")

    def plan(self, **kwargs: Any) -> AdaptivePlan:
        return self.decide(**kwargs)

    def _resume_decision(self, goal_id: str, subgoal: Mapping[str, Any], state: str) -> AdaptivePlan:
        subgoal_id = self._required_id(subgoal, "subgoal_id")
        resume_point = copy.deepcopy(subgoal.get("resume_point"))
        if state == "blocked":
            transition = GoalTransition(
                "subgoal",
                subgoal_id,
                "blocked",
                "resumable",
                "resume_ready",
                "blocked_subgoal_resume_requested",
                resume_point,
            )
            result = self.state_machine.transition(transition)
            if not result.accepted:
                return self._rejected(goal_id, subgoal_id, result)
            return self._plan(
                goal_id,
                subgoal_id,
                "resume_blocked",
                "blocked_subgoal_has_valid_resume_transition",
                transition=transition,
                review=self.policy.require_review_for_resume or result.requires_user_review,
            )

        if self.policy.prevent_runtime_bypass:
            return self._plan(
                goal_id,
                subgoal_id,
                "wait_for_user",
                "resumable_activation_requires_runtime_adaptive",
                review=True,
            )

        return self._plan(
            goal_id,
            subgoal_id,
            "resume_blocked",
            "resumable_subgoal_ready_for_external_resume",
            review=self.policy.require_review_for_resume,
        )

    @staticmethod
    def _record(value: Mapping[str, Any] | Any) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return copy.deepcopy(dict(value))
        if hasattr(value, "to_dict"):
            return copy.deepcopy(dict(value.to_dict()))
        raise TypeError("adaptive_planner_inputs_must_be_mappings_or_records")

    @staticmethod
    def _required_id(record: Mapping[str, Any], field: str) -> str:
        value = str(record.get(field) or "").strip()
        if not value:
            raise ValueError(f"adaptive_planner_requires_{field}")
        return value

    @staticmethod
    def _state(current_state: Mapping[str, Any] | str | None, record: Mapping[str, Any]) -> str:
        if isinstance(current_state, Mapping):
            value = current_state.get("status") or current_state.get("state")
        else:
            value = current_state
        return str(value or record.get("status") or record.get("state") or "").strip().lower()

    @staticmethod
    def _validated_ref(evidence_id: Any) -> dict[str, Any]:
        return {
            "evidence_id": str(evidence_id),
            "validation_state": "validated",
        }

    @staticmethod
    def _evidence_status(
        summary: EvidenceChain | Mapping[str, Any] | Sequence[Any] | None,
        goal: Mapping[str, Any],
    ) -> tuple[list[Any], int]:
        if isinstance(summary, EvidenceChain):
            return (
                [AdaptivePlanner._validated_ref(item) for item in summary.validated_evidence_ids],
                summary.rejected_count,
            )

        if isinstance(summary, Mapping):
            values = summary.get("records") or summary.get("evidence") or summary.get("items") or []
            validation_summary = summary.get("validation_summary")
            validation_summary = validation_summary if isinstance(validation_summary, Mapping) else {}
            rejected_count = int(
                summary.get("rejected_count")
                or validation_summary.get("rejected", 0)
            )
            validated_ids = summary.get("validated_evidence_ids") or []
            has_validated = bool(
                summary.get("has_validated_evidence")
                or validated_ids
                or validation_summary.get("validated", 0)
            )
            if not values and has_validated:
                ids = list(validated_ids or summary.get("evidence_ids") or [])
                return [AdaptivePlanner._validated_ref(item) for item in ids], rejected_count
        else:
            values = summary
            rejected_count = 0

        candidates = list(values if values is not None else goal.get("evidence_refs") or [])
        validated: list[Any] = []

        for item in candidates:
            if isinstance(item, EvidenceRecord):
                if item.validation_state == "validated":
                    validated.append(AdaptivePlanner._validated_ref(item.evidence_id))
                elif item.validation_state == "rejected":
                    rejected_count += 1
            elif isinstance(item, Mapping):
                validation_state = str(item.get("validation_state") or "").strip().lower()
                if validation_state == "validated":
                    validated.append(copy.deepcopy(dict(item)))
                elif validation_state == "rejected":
                    rejected_count += 1

        return validated, rejected_count

    @staticmethod
    def _select_subgoal(subgoals: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
        for state in ("blocked", "resumable", "active", "pending"):
            selected = next((item for item in subgoals if AdaptivePlanner._state(None, item) == state), None)
            if selected is not None:
                return copy.deepcopy(dict(selected))
        return None

    @staticmethod
    def _first_incomplete_id(subgoals: Sequence[Mapping[str, Any]]) -> str | None:
        item = next((item for item in subgoals if AdaptivePlanner._state(None, item) != "completed"), None)
        return str(item.get("subgoal_id") or "") or None if item else None

    @staticmethod
    def _blocker_reason(summary: Mapping[str, Any] | Sequence[Any] | str | None, subgoal: Mapping[str, Any]) -> str | None:
        if isinstance(summary, str):
            return summary.strip() or None
        if isinstance(summary, Mapping):
            value = summary.get("reason") or summary.get("blocked_reason")
            return str(value).strip() or None if value else None
        if summary:
            return "blocker_summary_present"
        value = subgoal.get("blocked_reason")
        return str(value).strip() or None if value else None

    @staticmethod
    def _transition_dict(transition: GoalTransition | Mapping[str, Any]) -> dict[str, Any]:
        if isinstance(transition, Mapping):
            return copy.deepcopy(dict(transition))
        return {
            "target_type": transition.target_type,
            "target_id": transition.target_id,
            "from_state": transition.from_state,
            "to_state": transition.to_state,
            "action": transition.action,
            "reason": transition.reason,
            "resume_point": copy.deepcopy(transition.resume_point),
            "evidence_refs": copy.deepcopy(transition.evidence_refs),
            "requires_user_review": transition.requires_user_review,
        }

    @staticmethod
    def _completion_transition_dict(goal_id: str, result: Any) -> dict[str, Any]:
        return {
            "target_type": "goal",
            "target_id": goal_id,
            "from_state": result.from_state,
            "to_state": result.to_state,
            "action": "complete",
            "reason": result.reason,
            "resume_point": None,
            "evidence_refs": copy.deepcopy(result.evidence_refs),
            "requires_user_review": result.requires_user_review,
            "completion_authority": "GoalCompletionAuthority",
        }

    def _rejected(self, goal_id: str, subgoal_id: str, result: GoalTransitionResult) -> AdaptivePlan:
        return self._plan(
            goal_id,
            subgoal_id,
            "wait_for_user" if result.requires_user_review else "no_action",
            result.blocked_reason or result.reason,
            review=result.requires_user_review,
        )

    def _plan(
        self,
        goal_id: str,
        subgoal_id: str | None,
        decision_type: str,
        reason: str,
        *,
        transition: GoalTransition | Mapping[str, Any] | None = None,
        review: bool = False,
        evidence_required: list[Any] | None = None,
    ) -> AdaptivePlan:
        return AdaptivePlan(
            selected_goal_id=goal_id,
            selected_subgoal_id=subgoal_id,
            decision_type=decision_type,
            reason=reason,
            required_transition=self._transition_dict(transition) if transition is not None else None,
            requires_user_review=review,
            evidence_required=evidence_required or [],
        )


__all__ = ["AdaptivePlanner"]