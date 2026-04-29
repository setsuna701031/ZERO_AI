from __future__ import annotations

import copy
from typing import Any, Dict


GUARDED_MODES = {"task_loop", "task_loop_until_terminal"}
REPLAN_ACTIONS = {"replan"}


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_decision_mode(*values: Any) -> str:
    for value in values:
        text = _safe_text(value).lower()
        if text:
            return text
    return ""


def infer_decision_mode(
    task: Any = None,
    runner_result: Any = None,
    local_observation: Any = None,
) -> str:
    task_dict = task if isinstance(task, dict) else {}
    result = runner_result if isinstance(runner_result, dict) else {}
    local = local_observation if isinstance(local_observation, dict) else {}

    return normalize_decision_mode(
        task_dict.get("decision_guard_mode"),
        task_dict.get("loop_mode"),
        task_dict.get("execution_mode"),
        result.get("decision_guard_mode"),
        result.get("mode"),
        local.get("decision_guard_mode"),
        local.get("mode"),
    )


def guard_loop_decision(decision: Any, *, mode: str = "") -> Dict[str, Any]:
    guarded = copy.deepcopy(decision) if isinstance(decision, dict) else {}
    normalized_mode = normalize_decision_mode(mode)
    guarded["decision_guard_mode"] = normalized_mode

    if normalized_mode not in GUARDED_MODES:
        return guarded

    decision_name = _safe_text(guarded.get("decision")).lower()
    next_action = _safe_text(guarded.get("next_action")).lower()
    should_replan = bool(guarded.get("should_replan"))

    if decision_name not in REPLAN_ACTIONS and next_action not in REPLAN_ACTIONS and not should_replan:
        return guarded

    original = copy.deepcopy(guarded)
    reason = _safe_text(guarded.get("reason")) or "replan decision is not allowed in task loop mode"

    guarded.update(
        {
            "decision": "fail",
            "next_action": "finish",
            "terminal": True,
            "should_continue": False,
            "should_replan": False,
            "should_fail": True,
            "reason": f"decision guard blocked replan in {normalized_mode}: {reason}",
            "guarded": True,
            "guard_reason": "replan_not_allowed_in_task_loop",
            "original_decision": original,
        }
    )
    return guarded
