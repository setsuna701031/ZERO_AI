from __future__ import annotations

import copy
from typing import Any, Dict, List

from core.runtime.task_runtime import project_runtime_status
from core.tools.execution_trace import ExecutionTrace
from core.tasks.scheduler_core.trace_helpers import trace_step


def _handle_simple_step_exception(
    scheduler,
    task: Dict[str, Any],
    trace: ExecutionTrace,
    task_id: str,
    task_name: str,
    current_step_index: int,
    step: Dict[str, Any],
    error: Exception,
    execution_log: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    step_results: List[Dict[str, Any]],
    last_step_result: Any,
) -> Dict[str, Any]:
    failed_step_result = {
        "ok": False,
        "step_index": current_step_index,
        "step": copy.deepcopy(step),
        "error": str(error),
    }
    execution_log.append(
        {
            "tick": scheduler.current_tick,
            "step_index": current_step_index,
            "step": copy.deepcopy(step),
            "ok": False,
            "error": str(error),
        }
    )
    results.append(copy.deepcopy(failed_step_result))
    step_results = copy.deepcopy(results)
    last_step_result = copy.deepcopy(failed_step_result)

    task["execution_log"] = execution_log
    task["results"] = results
    task["step_results"] = step_results
    task["last_step_result"] = last_step_result
    task["last_error"] = str(error)
    task["failure_message"] = str(error)
    task["last_failure_tick"] = scheduler.current_tick
    task["last_run_tick"] = scheduler.current_tick

    trace_step(
        scheduler=scheduler,
        trace=trace,
        task=task,
        step_index=current_step_index,
        step=step,
        ok=False,
        result=None,
        error=str(error),
        tick=scheduler.current_tick,
    )

    replan_result = scheduler._try_replan_task(task=task)
    task["replan_decision"] = str(replan_result.get("decision") or "")
    task["replan_summary"] = str(replan_result.get("summary") or "")
    task["replan_failed_step_type"] = str(replan_result.get("failed_step_type") or "")
    task["replan_repairable"] = replan_result.get("repairable", None)

    if replan_result.get("replanned"):
        project_runtime_status(task, "queued", owner="core/tasks/scheduler_core/simple_runner_helpers.py")
        task["replan_reason"] = str(task.get("last_error") or task.get("failure_message") or str(error))
        task["current_step_index"] = 0
        task["history"] = scheduler._append_history(task.get("history"), "replanned")
        task["history"] = scheduler._append_history(task.get("history"), "queued")

        new_steps = task.get("steps", []) if isinstance(task.get("steps"), list) else []
        new_steps_total = len(new_steps)

        scheduler._trace_replan(
            trace=trace,
            task=task,
            tick=scheduler.current_tick,
            replan_result=replan_result,
        )
        scheduler._trace_status(
            trace=trace,
            task=task,
            status="queued",
            tick=scheduler.current_tick,
            final_answer="",
            extra={
                "action": "simple_step_replanned",
                "replan_reason": task["replan_reason"],
                "replan_count": task.get("replan_count", 0),
                "replan_decision": task.get("replan_decision", ""),
                "replan_summary": task.get("replan_summary", ""),
                "replan_failed_step_type": task.get("replan_failed_step_type", ""),
                "replan_repairable": task.get("replan_repairable", None),
                "steps_total": new_steps_total,
            },
        )
        scheduler._save_trace_for_task(task=task, trace=trace)

        return {
            "ok": True,
            "action": "simple_step_replanned",
            "tick": scheduler.current_tick,
            "task_id": task_id,
            "task_name": task_name,
            "status": "queued",
            "message": replan_result.get("summary", "task replanned"),
            "execution_log": execution_log,
            "results": results,
            "step_results": step_results,
            "last_step_result": last_step_result,
            "current_step_index": 0,
            "step_count": new_steps_total,
            "steps_total": new_steps_total,
            "last_run_tick": scheduler.current_tick,
            "last_failure_tick": scheduler.current_tick,
            "replan_reason": task["replan_reason"],
            "replan_decision": task.get("replan_decision", ""),
            "replan_summary": task.get("replan_summary", ""),
            "replan_failed_step_type": task.get("replan_failed_step_type", ""),
            "replan_repairable": task.get("replan_repairable", None),
            "replan_result": replan_result,
        }

    project_runtime_status(task, "failed", owner="core/tasks/scheduler_core/simple_runner_helpers.py")
    task["history"] = scheduler._append_history(task.get("history"), "failed")

    scheduler._trace_status(
        trace=trace,
        task=task,
        status="failed",
        tick=scheduler.current_tick,
        final_answer="",
        extra={
            "action": "simple_step_failed",
            "error": str(error),
            "replan_decision": task.get("replan_decision", ""),
            "replan_summary": task.get("replan_summary", ""),
            "replan_failed_step_type": task.get("replan_failed_step_type", ""),
            "replan_repairable": task.get("replan_repairable", None),
            "replan_result": copy.deepcopy(replan_result),
        },
    )
    scheduler._save_trace_for_task(task=task, trace=trace)

    return {
        "ok": False,
        "action": "simple_step_failed",
        "tick": scheduler.current_tick,
        "task_id": task_id,
        "task_name": task_name,
        "status": "failed",
        "message": "step execution failed",
        "error": str(error),
        "execution_log": execution_log,
        "results": results,
        "step_results": step_results,
        "last_step_result": last_step_result,
        "current_step_index": current_step_index,
        "step_count": len(task.get("steps", [])) if isinstance(task.get("steps"), list) else 0,
        "steps_total": len(task.get("steps", [])) if isinstance(task.get("steps"), list) else 0,
        "last_run_tick": scheduler.current_tick,
        "last_failure_tick": scheduler.current_tick,
        "replan_decision": task.get("replan_decision", ""),
        "replan_summary": task.get("replan_summary", ""),
        "replan_failed_step_type": task.get("replan_failed_step_type", ""),
        "replan_repairable": task.get("replan_repairable", None),
        "replan_result": replan_result,
    }


