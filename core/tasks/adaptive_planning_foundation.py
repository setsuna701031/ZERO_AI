from __future__ import annotations

"""Normalized, decision-only adaptive planning contracts."""

import copy
from typing import Any, Mapping


ADAPTIVE_PLANNING_RECORD_SCHEMA = "zero.adaptive_planning.record.v1"
OUTCOME_CLASSES = frozenset({
    "success",
    "partial_success",
    "recoverable_failure",
    "unrecoverable_failure",
    "blocked",
    "waiting",
})
ADAPTIVE_ACTIONS = frozenset({
    "continue_current_plan",
    "create_followup_goal",
    "request_replan",
    "stop",
})

_BLOCKED_STATES = frozenset({"blocked", "denied"})
_WAITING_STATES = frozenset({"waiting", "pending", "queued", "paused"})
_SUCCESS_STATES = frozenset({"complete", "completed", "success", "succeeded"})
_RECOVERABLE_STATES = frozenset({"replan", "recoverable_failure", "retryable_failure"})


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def classify_runtime_outcome(
    runtime_result: Mapping[str, Any],
    *,
    progress: Mapping[str, Any] | None = None,
) -> str:
    """Classify a runtime pass without executing, retrying, or persisting."""

    result = _mapping(runtime_result)
    facts = _mapping(progress)
    runtime_state = _text(result.get("state") or result.get("decision_state")).lower()
    goal_state = _text(facts.get("goal_state")).lower()
    if facts.get("blocking_failure") or facts.get("blocked") or runtime_state in _BLOCKED_STATES or goal_state in _BLOCKED_STATES:
        return "blocked"
    if runtime_state in _WAITING_STATES or goal_state in _WAITING_STATES:
        return "waiting"
    if facts.get("complete") or (bool(result.get("ok")) and runtime_state in _SUCCESS_STATES):
        return "success"
    if bool(result.get("ok")):
        return "partial_success"
    if facts.get("recoverable_failure") or runtime_state in _RECOVERABLE_STATES:
        return "recoverable_failure"
    return "unrecoverable_failure"


def evaluate_runtime_outcome(
    runtime_result: Mapping[str, Any],
    *,
    progress: Mapping[str, Any] | None = None,
    previous_goal: Any = None,
    previous_step: Any = None,
    replan_count: int = 0,
    continuation_count: int = 0,
    max_replans: int = 1,
    max_continuations: int = 3,
) -> dict[str, Any]:
    """Return a bounded adaptive decision record for a completed runtime pass."""

    outcome_class = classify_runtime_outcome(runtime_result, progress=progress)
    replans = max(0, int(replan_count or 0))
    continuations = max(0, int(continuation_count or 0))
    replan_limit = max(0, int(max_replans or 0))
    continuation_limit = max(0, int(max_continuations or 0))
    refused = False
    refusal_reason = ""

    if outcome_class == "success":
        next_action, reason = "stop", "runtime_outcome_success"
    elif outcome_class == "partial_success":
        next_action, reason = "create_followup_goal", "runtime_outcome_partial_success"
        if continuations >= continuation_limit:
            next_action, refused, refusal_reason = "stop", True, "max_continuations_exhausted"
            reason = refusal_reason
    elif outcome_class == "waiting":
        next_action, reason = "continue_current_plan", "runtime_outcome_waiting"
        if continuations >= continuation_limit:
            next_action, refused, refusal_reason = "stop", True, "max_continuations_exhausted"
            reason = refusal_reason
    elif outcome_class == "recoverable_failure":
        next_action, reason = "request_replan", "runtime_outcome_recoverable_failure"
        if replans >= replan_limit:
            next_action, refused, refusal_reason = "stop", True, "max_replans_exhausted"
            reason = refusal_reason
    elif outcome_class == "blocked":
        next_action, reason = "stop", "runtime_outcome_blocked"
    else:
        next_action, reason = "stop", "runtime_outcome_unrecoverable_failure"

    return {
        "schema": ADAPTIVE_PLANNING_RECORD_SCHEMA,
        "previous_goal": copy.deepcopy(previous_goal),
        "previous_step": copy.deepcopy(previous_step),
        "outcome_class": outcome_class,
        "decision_reason": reason,
        "next_action": next_action,
        "replan_count": replans,
        "continuation_count": continuations,
        "max_replans": replan_limit,
        "max_continuations": continuation_limit,
        "refused": refused,
        "refusal_reason": refusal_reason,
        "execution_path": {
            "decision_only": True,
            "executes_tasks": False,
            "persists_records": False,
            "direct_tool_execution": False,
            "hidden_retry_loop": False,
        },
    }


__all__ = [
    "ADAPTIVE_ACTIONS",
    "ADAPTIVE_PLANNING_RECORD_SCHEMA",
    "OUTCOME_CLASSES",
    "classify_runtime_outcome",
    "evaluate_runtime_outcome",
]
