from __future__ import annotations

import copy
from typing import Any, Dict, List

from core.tools.execution_trace import ExecutionTrace
from core.tasks.scheduler_core.simple_runner_result_helpers import (
    _build_simple_failed_step_result,
    _build_simple_step_failed_payload,
    _build_simple_step_replanned_payload,
    _sync_simple_failed_step_collections,
)
from core.tasks.scheduler_core.simple_runner_state_mutation_helpers import (
    _apply_simple_failure_fields,
    _apply_simple_replanned_queued_state,
    _apply_simple_step_collections_to_task,
    _apply_simple_terminal_failed_state,
)
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
    failed_step_result = _build_simple_failed_step_result(
        current_step_index,
        step,
        error,
    )
    step_results, last_step_result = _sync_simple_failed_step_collections(
        tick=scheduler.current_tick,
        current_step_index=current_step_index,
        step=step,
        error=error,
        execution_log=execution_log,
        results=results,
        failed_step_result=failed_step_result,
    )

    _apply_simple_step_collections_to_task(
        task,
        execution_log=execution_log,
        results=results,
        step_results=step_results,
        last_step_result=last_step_result,
    )
    _apply_simple_failure_fields(scheduler, task, error)

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
        _apply_simple_replanned_queued_state(scheduler, task, error)

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

        return _build_simple_step_replanned_payload(
            tick=scheduler.current_tick,
            task_id=task_id,
            task_name=task_name,
            message=replan_result.get("summary", "task replanned"),
            execution_log=execution_log,
            results=results,
            step_results=step_results,
            last_step_result=last_step_result,
            steps_total=new_steps_total,
            replan_reason=task["replan_reason"],
            replan_decision=task.get("replan_decision", ""),
            replan_summary=task.get("replan_summary", ""),
            replan_failed_step_type=task.get("replan_failed_step_type", ""),
            replan_repairable=task.get("replan_repairable", None),
            replan_result=replan_result,
        )

    _apply_simple_terminal_failed_state(scheduler, task)

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

    step_count = len(task.get("steps", [])) if isinstance(task.get("steps"), list) else 0
    return _build_simple_step_failed_payload(
        tick=scheduler.current_tick,
        task_id=task_id,
        task_name=task_name,
        error=error,
        execution_log=execution_log,
        results=results,
        step_results=step_results,
        last_step_result=last_step_result,
        current_step_index=current_step_index,
        step_count=step_count,
        replan_decision=task.get("replan_decision", ""),
        replan_summary=task.get("replan_summary", ""),
        replan_failed_step_type=task.get("replan_failed_step_type", ""),
        replan_repairable=task.get("replan_repairable", None),
        replan_result=replan_result,
    )


