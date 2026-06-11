from __future__ import annotations

import copy
from typing import Any, Dict, Optional


def is_autonomous_repair_chain_payload(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    step = value.get("step") if isinstance(value.get("step"), dict) else value
    step_type = str(step.get("type") or step.get("action") or value.get("step_type") or "").strip().lower()
    return step_type in {"autonomous_repair_chain", "runtime_autonomous_repair_chain"} or bool(value.get("autonomous_repair_chain"))


def attach_autonomous_repair_chain_summary(target: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(target, dict):
        return target
    candidates = []
    for key in ("last_result", "last_step_result", "result"):
        if isinstance(target.get(key), dict):
            candidates.append(target.get(key))
    for item in target.get("results") or []:
        if isinstance(item, dict):
            candidates.append(item)
    for item in candidates:
        if not isinstance(item, dict):
            continue
        result = item.get("result") if isinstance(item.get("result"), dict) else item
        inner = result.get("result") if isinstance(result.get("result"), dict) else result
        if is_autonomous_repair_chain_payload(item) or str(inner.get("runtime_phase") or "") == "autonomous_repair_chaining_v2":
            summary = {
                "ok": bool(inner.get("ok", result.get("ok", False))),
                "runtime_phase": "autonomous_repair_chaining_v2",
                "status": str(inner.get("status") or result.get("status") or ""),
                "repair_chain_id": str(inner.get("repair_chain_id") or result.get("repair_chain_id") or ""),
                "attempt_count": int(inner.get("attempt_count") or 0),
                "retry_count": int(inner.get("retry_count") or 0),
            }
            target["autonomous_repair_chain_summary"] = summary
            target["runtime_autonomous_repair_chain_v2"] = True
            if not summary["ok"] and summary["status"] == "retry_limit_reached":
                target["retryable"] = False
                target.setdefault("replan_blocked_reason", "autonomous_repair_retry_limit_reached")
            return target
    return target


def norm_text(value: Any) -> str:
    return str(value or "").strip()


def scheduler_step_type(step: Any) -> str:
    if isinstance(step, dict):
        return norm_text(step.get("type") or step.get("action")).lower()
    return ""


def scheduler_direct_step(scheduler: Any, task: Any, current_tick: Any) -> dict[str, Any] | None:
    if not isinstance(task, dict):
        return None
    steps = task.get("steps")
    if not isinstance(steps, list) or not steps:
        return None
    try:
        index = int(task.get("current_step_index", 0) or 0)
    except Exception:
        index = 0
    if index < 0:
        index = 0
    if index >= len(steps):
        return {
            "ok": True,
            "action": "already_finished",
            "status": "finished",
            "task": copy.deepcopy(task),
            "current_step_index": len(steps),
            "step_count": len(steps),
            "steps_total": len(steps),
        }
    step = steps[index]
    if not isinstance(step, dict):
        return None

    return None


def _direct_step_success_payload(
    scheduler: Any,
    task: dict[str, Any],
    steps: list[Any],
    index: int,
    step_result: dict[str, Any],
) -> dict[str, Any]:
    updated_task = copy.deepcopy(task)
    normalized_step_result = {
        "ok": True,
        "step_index": index,
        "step": copy.deepcopy(steps[index]),
        "result": copy.deepcopy(step_result),
    }
    results = copy.deepcopy(updated_task.get("results")) if isinstance(updated_task.get("results"), list) else []
    results.append(normalized_step_result)
    execution_log = (
        copy.deepcopy(updated_task.get("execution_log"))
        if isinstance(updated_task.get("execution_log"), list)
        else []
    )
    execution_log.append({
        "tick": current_tick if (current_tick := getattr(scheduler, "current_tick", None)) is not None else 0,
        "step_index": index,
        "step": copy.deepcopy(steps[index]),
        "ok": True,
        "result": copy.deepcopy(step_result),
    })
    updated_task["results"] = results
    updated_task["step_results"] = copy.deepcopy(results)
    updated_task["last_step_result"] = copy.deepcopy(normalized_step_result)
    updated_task["execution_log"] = execution_log
    updated_task["current_step_index"] = min(index + 1, len(steps))
    if index + 1 >= len(steps):
        updated_task["status"] = "finished"
        status = "finished"
    else:
        updated_task["status"] = "queued"
        status = "queued"
    runtime_state = _save_runtime_state_if_available(scheduler, updated_task)
    _persist_task_payload_if_available(scheduler, updated_task)
    return {
        "ok": True,
        "action": "scheduler_step_executor_fallback",
        "status": status,
        "task_id": norm_text(task.get("task_id") or task.get("task_name")),
        "task": updated_task,
        "runtime_state": copy.deepcopy(runtime_state),
        "result": copy.deepcopy(step_result),
        "step_result": copy.deepcopy(normalized_step_result),
        "last_step_result": copy.deepcopy(normalized_step_result),
        "executed_results": [copy.deepcopy(step_result)],
        "results": copy.deepcopy(results),
        "step_results": copy.deepcopy(results),
        "execution_log": copy.deepcopy(execution_log),
        "current_step_index": updated_task["current_step_index"],
        "step_count": len(steps),
        "steps_total": len(steps),
        "final_answer": step_result.get("final_answer") or step_result.get("message") or "ok",
    }


def _direct_step_failure_payload(
    scheduler: Any,
    task: dict[str, Any],
    steps: list[Any],
    index: int,
    step_result: dict[str, Any],
) -> dict[str, Any]:
    blocked = bool(step_result.get("blocked"))
    failed_status = "blocked" if blocked else "failed"
    updated_task = copy.deepcopy(task)
    updated_task["status"] = failed_status
    updated_task["current_step_index"] = index
    updated_task["last_step_result"] = copy.deepcopy(step_result)
    updated_task.setdefault("results", [])
    updated_task.setdefault("step_results", [])
    try:
        updated_task["results"] = list(updated_task.get("results") or []) + [copy.deepcopy(step_result)]
        updated_task["step_results"] = list(updated_task.get("step_results") or []) + [copy.deepcopy(step_result)]
    except Exception:
        pass
    runtime_state = _save_runtime_state_if_available(scheduler, updated_task)
    _persist_task_payload_if_available(scheduler, updated_task)
    return {
        "ok": True,
        "action": "scheduler_step_executor_fallback_handled_failure",
        "status": failed_status,
        "task_id": norm_text(task.get("task_id") or task.get("task_name")),
        "task": updated_task,
        "runtime_state": copy.deepcopy(runtime_state),
        "result": copy.deepcopy(step_result),
        "step_result": copy.deepcopy(step_result),
        "last_step_result": copy.deepcopy(step_result),
        "executed_results": [copy.deepcopy(step_result)],
        "current_step_index": index,
        "step_count": len(steps),
        "steps_total": len(steps),
        "blocked": blocked,
        "failed": not blocked,
        "error": step_result.get("error") or step_result.get("message") or "step execution failed",
        "final_answer": step_result.get("final_answer") or step_result.get("message") or "step execution failed",
    }


def _save_runtime_state_if_available(scheduler: Any, updated_task: dict[str, Any]) -> dict[str, Any]:
    runtime_state = copy.deepcopy(updated_task)
    try:
        runtime = getattr(scheduler, "task_runtime", None)
        if runtime is not None and hasattr(runtime, "save_runtime_state"):
            runtime_state = runtime.save_runtime_state(updated_task, runtime_state)
    except Exception:
        runtime_state = copy.deepcopy(updated_task)
    return runtime_state


def _persist_task_payload_if_available(scheduler: Any, updated_task: dict[str, Any]) -> None:
    try:
        scheduler._persist_task_payload(
            task_id=norm_text(updated_task.get("task_id") or updated_task.get("task_name")),
            task=updated_task,
        )
    except Exception:
        pass


def apply_autonomous_repair_chain_overlay(Scheduler: Any) -> None:
    original_run_one_step = Scheduler.run_one_step

    def scheduler_run_one_step(self: Any, task: Dict[str, Any], current_tick: Optional[int] = None) -> Dict[str, Any]:
        result = original_run_one_step(self, task=task, current_tick=current_tick)
        if isinstance(result, dict):
            attach_autonomous_repair_chain_summary(result)
            for target in (task, result.get("task"), result.get("runtime_state")):
                if isinstance(target, dict):
                    attach_autonomous_repair_chain_summary(target)
        return result

    Scheduler.run_one_step = scheduler_run_one_step
    Scheduler._attach_autonomous_repair_chain_summary = attach_autonomous_repair_chain_summary


def apply_boundary_authority_overlay(Scheduler: Any) -> None:
    original_run_one_step = Scheduler.run_one_step

    def scheduler_run_one_step(self: Any, task: Any = None, current_tick: Any = None):
        result = original_run_one_step(self, task=task, current_tick=current_tick)
        if isinstance(result, dict) and result.get("ok") is True:
            return result
        if isinstance(result, dict) and result.get("action") == "retrying_repair_bridge_failed":
            return result
        fallback = scheduler_direct_step(self, task, current_tick)
        if isinstance(fallback, dict) and fallback.get("ok") is True:
            fallback["legacy_result"] = copy.deepcopy(result) if isinstance(result, dict) else result
            return fallback
        return result

    Scheduler.run_one_step = scheduler_run_one_step


__all__ = [
    "apply_autonomous_repair_chain_overlay",
    "apply_boundary_authority_overlay",
    "attach_autonomous_repair_chain_summary",
    "is_autonomous_repair_chain_payload",
    "norm_text",
    "scheduler_direct_step",
    "scheduler_step_type",
]
