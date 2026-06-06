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
ENGINEERING_REPLAN_REQUEST_SCHEMA = "zero.engineering_adaptive_planner.replan_request.v1"

ALLOWED_ADAPTIVE_DECISIONS = frozenset({"complete", "continue", "replan", "blocked"})
CONTINUE_ALIASES = frozenset({"retry", "again", "next", "resume", "loop"})
RECOVERABLE_MARKERS = (
    "missing_artifact",
    "missing artifact",
    "missing_output",
    "missing output",
    "empty_output",
    "empty output",
    "no_output",
    "no output",
    "artifact_not_found",
    "output_not_found",
    "replan",
    "repairable",
    "recoverable",
)
BLOCKING_MARKERS = (
    "blocking",
    "critical",
    "fatal",
    "unrecoverable",
    "manual_intervention_required",
    "permission_denied",
    "authority_denied",
)


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _goal_id(goal: Mapping[str, Any]) -> str:
    return _clean_text(goal.get("goal_id") or goal.get("task_id") or goal.get("package_id"))


def _clamp_confidence(value: Any, default: float = 0.75) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default
    return min(1.0, max(0.0, confidence))


def _contains_marker(value: Any, markers: tuple[str, ...]) -> bool:
    text = repr(value).lower() if isinstance(value, Mapping) else str(value or "").lower()
    return any(marker in text for marker in markers)


def _normalize_decision_name(value: Any) -> str:
    decision = _clean_text(value).lower()
    if decision in ALLOWED_ADAPTIVE_DECISIONS:
        return decision
    if decision in CONTINUE_ALIASES:
        return "continue"
    return "blocked"


def normalize_adaptive_decision(decision: Mapping[str, Any]) -> dict[str, Any]:
    """Return the strict Adaptive Planning v1 decision contract."""

    raw = _as_mapping(decision)
    normalized_decision = _normalize_decision_name(raw.get("decision"))
    reason = _clean_text(raw.get("reason"))
    if not reason:
        reason = "invalid_adaptive_decision" if normalized_decision == "blocked" else f"{normalized_decision}_requested"

    return {
        **raw,
        "decision": normalized_decision,
        "reason": reason,
        "confidence": _clamp_confidence(raw.get("confidence")),
        "next_action": _clean_text(raw.get("next_action")),
        "continuation_plan": copy.deepcopy(_as_mapping(raw.get("continuation_plan"))),
        "replan_request": copy.deepcopy(_as_mapping(raw.get("replan_request"))),
        "blocking_issues": copy.deepcopy(_as_list(raw.get("blocking_issues"))),
    }


class EngineeringAdaptivePlanner:
    """Decide whether a completed runtime pass finished or needs follow-up."""

    def evaluate_goal_progress(
        self,
        *,
        goal: Mapping[str, Any],
        runtime_result: Mapping[str, Any],
        runtime_root_cause: Mapping[str, Any] | None = None,
        issue_summary: Mapping[str, Any] | None = None,
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
        issues = _as_mapping(issue_summary)
        blocking_issues = _as_list(issues.get("blocking_issues"))

        blocking_failure = (
            bool(blocking_issues)
            or bool(blocked_tasks)
            or runtime_state in {"blocked"}
            or _contains_marker(root_cause, BLOCKING_MARKERS)
            or any(_contains_marker(item, BLOCKING_MARKERS) for item in failed_tasks)
        )
        complete = (
            runtime_ok
            and goal_state == "completed"
            and not remaining_tasks
            and not failed_tasks
            and not blocked_tasks
            and not blocking_failure
        )
        recoverable_failure = (
            runtime_state in {"replan"}
            or _contains_marker(root_cause, RECOVERABLE_MARKERS)
            or any(_contains_marker(item, RECOVERABLE_MARKERS) for item in failed_tasks)
        )
        next_runtime_request = self._next_runtime_request(runtime_result)
        incomplete_with_next_request = runtime_ok and bool(next_runtime_request) and not complete
        return {
            "schema": ENGINEERING_ADAPTIVE_PLANNER_SCHEMA,
            "goal_id": _goal_id(goal) or _clean_text(lifecycle.get("goal_id")),
            "runtime_ok": runtime_ok,
            "runtime_state": runtime_state,
            "goal_state": goal_state,
            "complete": complete,
            "blocked": blocking_failure,
            "remaining_tasks": copy.deepcopy(remaining_tasks),
            "completed_tasks": copy.deepcopy(completed_tasks),
            "failed_tasks": copy.deepcopy(failed_tasks),
            "blocked_tasks": copy.deepcopy(blocked_tasks),
            "progress": copy.deepcopy(progress),
            "root_cause": copy.deepcopy(root_cause),
            "blocking_issues": copy.deepcopy(blocking_issues),
            "blocking_failure": blocking_failure,
            "recoverable_failure": recoverable_failure,
            "next_runtime_request": copy.deepcopy(next_runtime_request),
            "incomplete_with_next_request": incomplete_with_next_request,
            "updated_at": time.time(),
        }

    def decide_next_action(
        self,
        *,
        goal: Mapping[str, Any],
        runtime_result: Mapping[str, Any],
        runtime_root_cause: Mapping[str, Any] | None = None,
        issue_summary: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        progress = self.evaluate_goal_progress(
            goal=goal,
            runtime_result=runtime_result,
            runtime_root_cause=runtime_root_cause,
            issue_summary=issue_summary,
        )
        if progress["complete"]:
            decision = "complete"
            reason = "goal_completed"
            confidence = 0.95
        elif progress["blocking_failure"]:
            decision = "blocked"
            reason = _clean_text(_as_mapping(runtime_root_cause).get("stop_reason"), "blocking_issue_or_unrecoverable_failure")
            confidence = 0.9
        elif progress["incomplete_with_next_request"]:
            decision = "continue"
            reason = "next_runtime_request_available"
            confidence = 0.85
        elif not progress["runtime_ok"] or progress["recoverable_failure"]:
            decision = "replan"
            reason = _clean_text(_as_mapping(runtime_root_cause).get("stop_reason"), "recoverable_runtime_failure")
            confidence = 0.8
        else:
            decision = "continue"
            reason = "goal_incomplete"
            confidence = 0.75

        continuation_plan = (
            self.build_continuation_plan(goal=goal, runtime_result=runtime_result, progress=progress)
            if decision == "continue"
            else {}
        )
        replan_request = (
            self.build_replan_request(goal=goal, runtime_result=runtime_result, progress=progress, reason=reason)
            if decision == "replan"
            else {}
        )
        normalized = normalize_adaptive_decision({
            "schema": ENGINEERING_ADAPTIVE_DECISION_SCHEMA,
            "decision": decision,
            "reason": reason,
            "confidence": confidence,
            "next_action": self._next_action_for_decision(decision),
            "goal_id": progress["goal_id"],
            "terminal": decision in {"complete", "blocked"},
            "continue_requested": decision == "continue",
            "complete_requested": decision == "complete",
            "blocked": decision == "blocked",
            "progress": progress,
            "continuation_plan": continuation_plan,
            "replan_request": replan_request,
            "blocking_issues": copy.deepcopy(_as_list(progress.get("blocking_issues"))),
            "root_cause": copy.deepcopy(_as_mapping(runtime_root_cause) if decision in {"blocked", "replan"} else {}),
            "execution_path": {
                "adaptive_planner_decides_only": True,
                "executes_tasks": False,
                "persists_goal": False,
                "runtime_orchestrator_loop_owner": False,
            },
            "updated_at": time.time(),
        })
        normalized["terminal"] = normalized["decision"] in {"complete", "blocked"}
        normalized["continue_requested"] = normalized["decision"] == "continue"
        normalized["complete_requested"] = normalized["decision"] == "complete"
        normalized["blocked"] = normalized["decision"] == "blocked"
        return normalized

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

    def build_replan_request(
        self,
        *,
        goal: Mapping[str, Any],
        runtime_result: Mapping[str, Any],
        progress: Mapping[str, Any] | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        progress_record = _as_mapping(progress) or self.evaluate_goal_progress(goal=goal, runtime_result=runtime_result)
        goal_id = _goal_id(goal) or _clean_text(progress_record.get("goal_id"))
        return {
            "schema": ENGINEERING_REPLAN_REQUEST_SCHEMA,
            "goal_id": goal_id,
            "reason": _clean_text(reason, "recoverable_runtime_failure"),
            "runtime_state": _clean_text(runtime_result.get("state")),
            "failed_tasks": copy.deepcopy(_as_list(progress_record.get("failed_tasks"))),
            "root_cause": copy.deepcopy(_as_mapping(progress_record.get("root_cause"))),
            "execution_path": {
                "request_only": True,
                "executes_tasks": False,
                "persists_goal": False,
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

    def _next_runtime_request(self, runtime_result: Mapping[str, Any]) -> dict[str, Any]:
        direct = _as_mapping(runtime_result.get("next_runtime_request"))
        if direct:
            return direct
        iterations = _as_list(runtime_result.get("iterations"))
        for item in reversed(iterations):
            if not isinstance(item, Mapping):
                continue
            for container_key in ("continuation_result", "planning_result", "lifecycle_result"):
                container = _as_mapping(item.get(container_key))
                request = _as_mapping(container.get("next_runtime_request"))
                if request:
                    return request
        return {}

    def _next_action_for_decision(self, decision: str) -> str:
        return {
            "complete": "",
            "continue": "create_continuation_work_item",
            "replan": "create_replan_record",
            "blocked": "stop_with_root_cause",
        }.get(decision, "stop_with_root_cause")


__all__ = [
    "ALLOWED_ADAPTIVE_DECISIONS",
    "ENGINEERING_ADAPTIVE_DECISION_SCHEMA",
    "ENGINEERING_ADAPTIVE_PLANNER_SCHEMA",
    "ENGINEERING_CONTINUATION_PLAN_SCHEMA",
    "ENGINEERING_REPLAN_REQUEST_SCHEMA",
    "EngineeringAdaptivePlanner",
    "normalize_adaptive_decision",
]
