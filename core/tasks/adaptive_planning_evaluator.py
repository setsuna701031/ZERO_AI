from __future__ import annotations

"""Decision-only adaptive planning evaluation.

AdaptivePlanningEvaluator inspects the latest continuation result and current
goal state, then returns a deterministic recommendation. It does not plan,
execute, persist memory, mutate lifecycle state, or dispatch agent routes.
"""

import copy
from typing import Any, Mapping


ADAPTIVE_PLANNING_EVALUATOR_SCHEMA = "zero.engineering_task.adaptive_planning_evaluator.v1"
ADAPTIVE_PLANNING_DECISION_SCHEMA = "zero.engineering_task.adaptive_planning_decision.v1"
VALID_DECISIONS = {"continue", "replan", "block", "complete"}


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _latest_bundle(latest_execution_result: Mapping[str, Any]) -> dict[str, Any]:
    latest = _as_mapping(latest_execution_result)
    result_bundle = _as_mapping(latest.get("result_bundle"))
    if result_bundle:
        return result_bundle
    latest_result = _as_mapping(latest.get("latest_result"))
    return _as_mapping(latest_result.get("result_bundle"))


def _status_from_result(latest_execution_result: Mapping[str, Any], bundle: Mapping[str, Any]) -> str:
    latest = _as_mapping(latest_execution_result)
    return _clean_text(
        latest.get("status")
        or latest.get("stopped_reason")
        or bundle.get("status")
        or bundle.get("stopped_reason")
    ).lower()


def _decision_record(decision: str, reason: str, *, signals: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": ADAPTIVE_PLANNING_DECISION_SCHEMA,
        "decision": decision,
        "reason": reason,
        "reasons": [reason],
        "terminal": decision in {"block", "complete"},
        "replan_requested": decision == "replan",
        "continue_requested": decision == "continue",
        "deterministic": True,
        "signals": copy.deepcopy(dict(signals)),
    }


class AdaptivePlanningEvaluator:
    """Evaluate whether planning should continue, replan, block, or complete."""

    schema = ADAPTIVE_PLANNING_EVALUATOR_SCHEMA

    def evaluate(
        self,
        *,
        latest_execution_result: Mapping[str, Any],
        current_goal_state: Mapping[str, Any],
        current_task_buckets: Mapping[str, Any],
        memory_summary: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        latest = _as_mapping(latest_execution_result)
        lifecycle = _as_mapping(current_goal_state)
        buckets = _as_mapping(current_task_buckets)
        memory = _as_mapping(memory_summary)
        bundle = _latest_bundle(latest)
        goal_state = _clean_text(lifecycle.get("goal_state")).lower()
        latest_status = _status_from_result(latest, bundle)
        remaining_tasks = _as_list(lifecycle.get("remaining_tasks"))
        blocked_tasks = _as_list(lifecycle.get("blocked_tasks"))
        failed_tasks = _as_list(lifecycle.get("failed_tasks"))
        pending_bucket = _as_list(buckets.get("pending"))

        explicit = _clean_text(
            latest.get("adaptive_planning_decision")
            or bundle.get("adaptive_planning_decision")
            or latest.get("next_adaptive_action")
            or bundle.get("next_adaptive_action")
        ).lower()
        if explicit in VALID_DECISIONS:
            return _decision_record(
                explicit,
                f"explicit_adaptive_decision:{explicit}",
                signals={
                    "goal_state": goal_state,
                    "latest_status": latest_status,
                    "remaining_count": len(remaining_tasks),
                    "pending_count": len(pending_bucket),
                    "memory_ref_count": len(_as_list(memory.get("records") or memory.get("memory_refs"))),
                },
            )

        if goal_state == "completed":
            return _decision_record(
                "complete",
                "goal_lifecycle_completed",
                signals={"goal_state": goal_state, "remaining_count": len(remaining_tasks)},
            )

        if bool(latest.get("unrecoverable")) or bool(bundle.get("unrecoverable")):
            return _decision_record(
                "block",
                "execution_result_unrecoverable",
                signals={"goal_state": goal_state, "latest_status": latest_status},
            )

        if goal_state == "cancelled":
            return _decision_record(
                "block",
                "goal_lifecycle_cancelled",
                signals={"goal_state": goal_state, "latest_status": latest_status},
            )

        if goal_state == "blocked" and bool(latest.get("terminal") or bundle.get("terminal")) and not blocked_tasks:
            return _decision_record(
                "block",
                "terminal_block_without_replannable_task",
                signals={"goal_state": goal_state, "latest_status": latest_status},
            )

        follow_up_requested = bool(latest.get("follow_up_planning_requested")) or bool(bundle.get("follow_up_planning_requested"))
        decision_items = _as_list(bundle.get("decisions"))
        decision_actions = [
            _clean_text(_as_mapping(item).get("next_action") or _as_mapping(item).get("decision")).lower()
            for item in decision_items
            if isinstance(item, Mapping)
        ]
        should_replan = (
            follow_up_requested
            or blocked_tasks
            or failed_tasks
            or latest_status in {"blocked", "failed", "blocked_or_failed", "runner_stopped_without_continuable_goal"}
            or any(action in {"replan", "plan_follow_up", "follow_up_planning", "replan_next_step"} for action in decision_actions)
        )
        if should_replan:
            if blocked_tasks:
                reason = "blocked_task"
            elif failed_tasks:
                reason = "failed_task"
            elif follow_up_requested or any(action in {"plan_follow_up", "follow_up_planning"} for action in decision_actions):
                reason = "execution_result_requests_follow_up_planning"
            elif any(action in {"replan", "replan_next_step"} for action in decision_actions):
                reason = "execution_result_requests_replan"
            else:
                reason = "execution_result_requires_replan"
            return _decision_record(
                "replan",
                reason,
                signals={
                    "goal_state": goal_state,
                    "latest_status": latest_status,
                    "blocked_count": len(blocked_tasks),
                    "failed_count": len(failed_tasks),
                    "follow_up_requested": follow_up_requested,
                    "decision_actions": decision_actions,
                },
            )

        if not remaining_tasks and not pending_bucket and goal_state in {"next_task_generated", "running", "task_selected"}:
            return _decision_record(
                "replan",
                "tasks_exhausted_goal_incomplete",
                signals={"goal_state": goal_state, "remaining_count": len(remaining_tasks), "pending_count": len(pending_bucket)},
            )

        return _decision_record(
            "continue",
            "continuation_can_proceed",
            signals={
                "goal_state": goal_state,
                "latest_status": latest_status,
                "remaining_count": len(remaining_tasks),
                "pending_count": len(pending_bucket),
            },
        )


__all__ = [
    "ADAPTIVE_PLANNING_DECISION_SCHEMA",
    "ADAPTIVE_PLANNING_EVALUATOR_SCHEMA",
    "AdaptivePlanningEvaluator",
    "VALID_DECISIONS",
]
