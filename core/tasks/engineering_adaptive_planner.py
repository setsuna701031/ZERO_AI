from __future__ import annotations

"""Post-runtime adaptive planning for engineering goals.

EngineeringAdaptivePlanner is a decision-only bridge after one runtime pass. It
does not execute tasks, mutate repository records, persist lifecycle state, or
enter the RuntimeOrchestrator loop.
"""

import copy
import time
from typing import Any, Mapping


ENGINEERING_ADAPTIVE_PLANNER_SCHEMA = "zero.engineering_adaptive_planner.v1"
ENGINEERING_ADAPTIVE_DECISION_SCHEMA = "zero.engineering_adaptive_planner.decision.v1"
ENGINEERING_CONTINUATION_PLAN_SCHEMA = "zero.engineering_adaptive_planner.continuation_plan.v1"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _goal_id(goal: Mapping[str, Any]) -> str:
    return _clean_text(goal.get("goal_id") or goal.get("task_id") or goal.get("package_id"))


class EngineeringAdaptivePlanner:
    """Decide whether a completed runtime pass finished or needs follow-up."""

    def evaluate_goal_progress(
        self,
        *,
        goal: Mapping[str, Any],
        runtime_result: Mapping[str, Any],
        runtime_root_cause: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        lifecycle = self._latest_lifecycle(runtime_result)
        progress = _as_mapping(lifecycle.get("progress"))
        completed_tasks = _as_list(lifecycle.get("completed_tasks"))
        remaining_tasks = _as_list(lifecycle.get("remaining_tasks"))
        failed_tasks = _as_list(lifecycle.get("failed_tasks"))
        blocked_tasks = _as_list(lifecycle.get("blocked_tasks"))
        goal_state = _clean_text(lifecycle.get("goal_state")).lower()
        runtime_state = _clean_text(runtime_result.get("state")).lower()
        runtime_ok = bool(runtime_result.get("ok"))
        root_cause = _as_mapping(runtime_root_cause)

        complete = runtime_ok and goal_state == "completed" and not remaining_tasks and not failed_tasks and not blocked_tasks
        blocked = (not runtime_ok) or bool(root_cause) or bool(failed_tasks) or bool(blocked_tasks) or runtime_state in {"blocked", "failed", "replan"}
        return {
            "schema": ENGINEERING_ADAPTIVE_PLANNER_SCHEMA,
            "goal_id": _goal_id(goal) or _clean_text(lifecycle.get("goal_id")),
            "runtime_ok": runtime_ok,
            "runtime_state": runtime_state,
            "goal_state": goal_state,
            "complete": complete,
            "blocked": blocked,
            "remaining_tasks": copy.deepcopy(remaining_tasks),
            "completed_tasks": copy.deepcopy(completed_tasks),
            "failed_tasks": copy.deepcopy(failed_tasks),
            "blocked_tasks": copy.deepcopy(blocked_tasks),
            "progress": copy.deepcopy(progress),
            "root_cause": copy.deepcopy(root_cause),
            "updated_at": time.time(),
        }

    def decide_next_action(
        self,
        *,
        goal: Mapping[str, Any],
        runtime_result: Mapping[str, Any],
        runtime_root_cause: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        progress = self.evaluate_goal_progress(
            goal=goal,
            runtime_result=runtime_result,
            runtime_root_cause=runtime_root_cause,
        )
        if progress["complete"]:
            decision = "complete"
            reason = "goal_completed"
        elif progress["blocked"]:
            decision = "blocked"
            reason = _clean_text(_as_mapping(runtime_root_cause).get("stop_reason"), "runtime_root_cause")
        else:
            decision = "continue"
            reason = "goal_incomplete"

        continuation_plan = (
            self.build_continuation_plan(goal=goal, runtime_result=runtime_result, progress=progress)
            if decision == "continue"
            else {}
        )
        return {
            "schema": ENGINEERING_ADAPTIVE_DECISION_SCHEMA,
            "decision": decision,
            "reason": reason,
            "goal_id": progress["goal_id"],
            "terminal": decision in {"complete", "blocked"},
            "continue_requested": decision == "continue",
            "complete_requested": decision == "complete",
            "blocked": decision == "blocked",
            "progress": progress,
            "continuation_plan": continuation_plan,
            "root_cause": copy.deepcopy(_as_mapping(runtime_root_cause) if decision == "blocked" else {}),
            "execution_path": {
                "adaptive_planner_decides_only": True,
                "executes_tasks": False,
                "persists_goal": False,
                "runtime_orchestrator_loop_owner": False,
            },
            "updated_at": time.time(),
        }

    def build_continuation_plan(
        self,
        *,
        goal: Mapping[str, Any],
        runtime_result: Mapping[str, Any],
        progress: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        progress_record = _as_mapping(progress) or self.evaluate_goal_progress(goal=goal, runtime_result=runtime_result)
        goal_id = _goal_id(goal) or _clean_text(progress_record.get("goal_id"))
        remaining_tasks = _as_list(progress_record.get("remaining_tasks"))
        payload = copy.deepcopy(_as_mapping(goal.get("payload")))
        payload.setdefault("goal_id", goal_id)
        payload.setdefault("task_id", goal_id)
        payload.setdefault("package_id", goal_id)
        payload.setdefault("goal", _clean_text(goal.get("summary") or goal.get("goal"), goal_id))
        payload.setdefault("task_type", "engineering_task")
        payload.setdefault("engineering_goal_lifecycle", True)
        payload["continuation_requested"] = True
        if remaining_tasks:
            payload["remaining_tasks"] = copy.deepcopy(remaining_tasks)
        return {
            "schema": ENGINEERING_CONTINUATION_PLAN_SCHEMA,
            "goal_id": goal_id,
            "reason": "goal_incomplete",
            "remaining_tasks": copy.deepcopy(remaining_tasks),
            "next_runtime_request": {
                "goal_id": goal_id,
                "payload": payload,
                "source_runtime_state": _clean_text(runtime_result.get("state")),
            },
            "execution_path": {
                "plan_only": True,
                "executes_tasks": False,
                "new_runtime_loop": False,
            },
            "created_at": time.time(),
        }

    def _latest_lifecycle(self, runtime_result: Mapping[str, Any]) -> dict[str, Any]:
        iterations = _as_list(runtime_result.get("iterations"))
        for item in reversed(iterations):
            if not isinstance(item, Mapping):
                continue
            continuation = _as_mapping(item.get("continuation_result"))
            lifecycle = _as_mapping(continuation.get("goal_lifecycle") or continuation.get("engineering_goal_lifecycle"))
            if lifecycle:
                return lifecycle
            planning = _as_mapping(item.get("planning_result"))
            lifecycle = _as_mapping(planning.get("goal_lifecycle") or planning.get("engineering_goal_lifecycle"))
            if lifecycle:
                return lifecycle
            lifecycle_result = _as_mapping(item.get("lifecycle_result"))
            lifecycle = _as_mapping(lifecycle_result.get("goal_lifecycle"))
            if lifecycle:
                return lifecycle
        return {}


__all__ = [
    "ENGINEERING_ADAPTIVE_DECISION_SCHEMA",
    "ENGINEERING_ADAPTIVE_PLANNER_SCHEMA",
    "ENGINEERING_CONTINUATION_PLAN_SCHEMA",
    "EngineeringAdaptivePlanner",
]
