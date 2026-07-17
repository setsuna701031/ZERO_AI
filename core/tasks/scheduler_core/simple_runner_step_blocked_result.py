from __future__ import annotations

import copy
from typing import Any, Dict, List

from core.runtime.task_runtime import project_runtime_status
from core.tools.execution_trace import ExecutionTrace
from core.tasks.scheduler_core.simple_runner_result_helpers import _build_simple_blocked_or_failed_payload
from core.tasks.scheduler_core.trace_helpers import trace_step


def _handle_simple_step_blocked_or_failed_result(
    scheduler,
    task: Dict[str, Any],
    trace: ExecutionTrace,
    task_id: str,
    task_name: str,
    current_step_index: int,
    step: Dict[str, Any],
    step_result: Dict[str, Any],
    steps: List[Dict[str, Any]],
    execution_log: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    step_results: List[Dict[str, Any]],
    last_step_result: Any,
    failure_signal: Dict[str, Any],
) -> Dict[str, Any]:
    blocked = bool(failure_signal.get("blocked"))
    error_type = str(failure_signal.get("error_type") or "step_execution_failed")
    message = str(failure_signal.get("message") or error_type or "step execution failed")
    status = getattr(scheduler, "STATUS_BLOCKED", "blocked") if blocked else "failed"
    action = "simple_step_blocked" if blocked else "simple_step_failed"

    normalized_step_result = {
        "ok": False,
        "step_index": current_step_index,
        "step_type": str(step.get("type") or step.get("action") or "").strip().lower(),
        "step": copy.deepcopy(step),
        "result": copy.deepcopy(step_result),
        "blocked": blocked,
        "failed": not blocked,
        "error_type": error_type,
        "message": message,
        "final_answer": message,
        "error": {
            "type": error_type,
            "message": message,
            "retryable": False,
        },
    }

    execution_log.append(
        {
            "tick": scheduler.current_tick,
            "step_index": current_step_index,
            "step": copy.deepcopy(step),
            "ok": False,
            "blocked": blocked,
            "failed": not blocked,
            "error_type": error_type,
            "message": message,
            "result": copy.deepcopy(step_result),
        }
    )
    results.append(copy.deepcopy(normalized_step_result))
    step_results = copy.deepcopy(results)
    last_step_result = copy.deepcopy(normalized_step_result)

    project_runtime_status(task, status, owner="core/tasks/scheduler_core/simple_runner_helpers.py")
    task["execution_log"] = execution_log
    task["results"] = results
    task["step_results"] = step_results
    task["last_step_result"] = last_step_result
    task["last_error"] = message
    task["failure_message"] = message
    task["failure_type"] = error_type
    task["state_detail"] = message
    task["last_run_tick"] = scheduler.current_tick
    task["current_step_index"] = current_step_index
    if blocked:
        task["blocked_reason"] = message
        task["next_action"] = "wait_for_external_event"
    else:
        task["last_failure_tick"] = scheduler.current_tick
    task["history"] = scheduler._append_history(task.get("history"), status)

    trace_step(
        scheduler=scheduler,
        trace=trace,
        task=task,
        step_index=current_step_index,
        step=step,
        ok=False,
        result=step_result,
        error=message,
        tick=scheduler.current_tick,
    )
    scheduler._trace_status(
        trace=trace,
        task=task,
        status=status,
        tick=scheduler.current_tick,
        final_answer="",
        extra={
            "action": action,
            "error": message,
            "error_type": error_type,
            "blocked": blocked,
            "current_step_index": current_step_index,
            "steps_total": len(steps),
        },
    )
    scheduler._save_trace_for_task(task=task, trace=trace)

    return _build_simple_blocked_or_failed_payload(
        tick=scheduler.current_tick,
        task_id=task_id,
        task_name=task_name,
        status=status,
        message=message,
        normalized_step_result=normalized_step_result,
        blocked=blocked,
        error_type=error_type,
        execution_log=execution_log,
        results=results,
        step_results=step_results,
        last_step_result=last_step_result,
        current_step_index=current_step_index,
        step_count=len(steps),
    )
