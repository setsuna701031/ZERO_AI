from __future__ import annotations

import copy
from typing import Any, Callable, Dict


RUNTIME_FRESHNESS_KEYS = (
    "status",
    "steps",
    "current_step_index",
    "steps_total",
    "results",
    "step_results",
    "execution_log",
    "execution_trace",
    "last_step_result",
    "last_error",
    "repair_context",
)

RETRY_REPLAY_STATUSES = {"retrying", "retry"}


def normalize_retry_status(task: Dict[str, Any]) -> str:
    if not isinstance(task, dict):
        return ""
    return str(task.get("status") or "").strip().lower()


def retry_replay_decision(
    task: Dict[str, Any],
    *,
    allows_auto_repair: Callable[[Dict[str, Any]], bool],
) -> Dict[str, Any]:
    status = normalize_retry_status(task)
    if status not in RETRY_REPLAY_STATUSES:
        return {"action": "delegate_original", "status": status, "reason": "not_retrying"}
    if not allows_auto_repair(task):
        return {"action": "delegate_original", "status": status, "reason": "auto_repair_not_allowed"}
    return {"action": "continue_replay", "status": status, "reason": "retry_repair_ready"}


def already_injected_decision(task: Dict[str, Any], repair_context: Dict[str, Any]) -> Dict[str, Any]:
    already_injected = bool(
        (isinstance(repair_context, dict) and repair_context.get("repair_steps_injected"))
        or (isinstance(task, dict) and task.get("repair_steps_injected"))
    )
    return {
        "action": "already_injected" if already_injected else "needs_repair_injection",
        "already_injected": already_injected,
        "enqueue_ready": already_injected,
    }


def repair_replacement_decision(
    repair_ok: bool,
    repair_steps: Any,
    repair_meta: Any,
) -> Dict[str, Any]:
    if not repair_ok:
        return {
            "action": "repair_injection_failed",
            "status": "failed",
            "repair_meta": repair_meta if isinstance(repair_meta, dict) else {},
            "enqueue_ready": False,
        }
    return {
        "action": "replace_failed_step",
        "status": "queued",
        "repair_steps": repair_steps if isinstance(repair_steps, list) else [],
        "repair_meta": repair_meta if isinstance(repair_meta, dict) else {},
        "enqueue_ready": True,
    }


def replay_enqueue_decision(action: str) -> Dict[str, Any]:
    return {
        "action": action,
        "enqueue_ready": action in {"already_injected", "replace_failed_step"},
        "overwrite": True,
    }


def replay_continuation_fields(
    *,
    status: str = "queued",
    next_action: str = "run_next_tick",
    last_decision: str = "continue",
    last_decision_reason: str = "repair_steps_injected",
) -> Dict[str, str]:
    return {
        "status": status,
        "next_action": next_action,
        "last_decision": last_decision,
        "last_decision_reason": last_decision_reason,
    }


def prepare_retrying_repair_replay_state(
    scheduler: Any,
    task: Dict[str, Any],
    *,
    read_runtime_state: Callable[[Dict[str, Any]], Dict[str, Any]],
    allows_auto_repair: Callable[[Dict[str, Any]], bool],
) -> Dict[str, Any]:
    task = scheduler._hydrate_task_from_workspace(copy.deepcopy(task)) if isinstance(task, dict) else {}
    if not isinstance(task, dict) or not task:
        return {
            "ok": False,
            "return_result": {
                "ok": False,
                "action": "retrying_repair_bridge_invalid_task",
                "status": "failed",
                "error": "invalid task",
            },
        }

    task_id = scheduler._extract_task_id(task)
    if not task_id:
        return {
            "ok": False,
            "return_result": {
                "ok": False,
                "action": "retrying_repair_bridge_missing_task_id",
                "status": "failed",
                "error": "missing task id",
            },
        }

    runtime_state = read_runtime_state(task)
    if isinstance(runtime_state, dict) and runtime_state:
        for key in RUNTIME_FRESHNESS_KEYS:
            if key in runtime_state:
                task[key] = copy.deepcopy(runtime_state.get(key))

    decision = retry_replay_decision(task, allows_auto_repair=allows_auto_repair)
    if decision["action"] == "delegate_original":
        return {
            "ok": True,
            "delegate_original": True,
            "task": task,
            "task_id": task_id,
            "runtime_state": runtime_state,
            "status": decision["status"],
            "decision": decision,
        }

    repair_context = task.get("repair_context") if isinstance(task.get("repair_context"), dict) else {}
    steps = task.get("steps") if isinstance(task.get("steps"), list) else []
    try:
        idx = int(task.get("current_step_index", 0) or 0)
    except Exception:
        idx = 0
    if idx < 0:
        idx = 0
    if idx >= len(steps):
        idx = max(0, len(steps) - 1)

    failed_step = steps[idx] if isinstance(steps, list) and 0 <= idx < len(steps) and isinstance(steps[idx], dict) else {}
    last_step = task.get("last_step_result")
    if isinstance(last_step, dict) and isinstance(last_step.get("step"), dict):
        failed_step = copy.deepcopy(last_step.get("step"))

    return {
        "ok": True,
        "delegate_original": False,
        "task": task,
        "task_id": task_id,
        "runtime_state": runtime_state,
        "status": decision["status"],
        "decision": decision,
        "repair_context": repair_context,
        "already_injected": already_injected_decision(task, repair_context),
        "steps": steps,
        "current_step_index": idx,
        "failed_step": failed_step,
    }
