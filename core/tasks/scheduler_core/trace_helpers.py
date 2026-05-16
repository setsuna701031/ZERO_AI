from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from core.tools.execution_trace import ExecutionTrace
from core.tasks.scheduler_core.trace_serialization_helpers import (
    _task_id,
    extract_execution_trace_from_payload,
    get_trace_file_for_task,
    load_trace_for_task,
    promote_execution_trace_in_executed_results,
    save_trace_for_task,
)


def trace_summary(
    scheduler: Any,
    trace: ExecutionTrace,
    task: Dict[str, Any],
    summary: str,
    tick: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    trace_runtime = getattr(scheduler, "trace_runtime", None)
    if trace_runtime is not None and hasattr(trace_runtime, "scheduler_trace_summary"):
        return trace_runtime.scheduler_trace_summary(
            scheduler=scheduler,
            trace=trace,
            task=task,
            summary=summary,
            tick=tick,
            extra=extra,
        )

    trace.add_summary_event(
        task_id=_task_id(scheduler, task),
        summary=summary,
        tick=tick,
        extra=copy.deepcopy(extra) if isinstance(extra, dict) else None,
    )
    return None


def trace_status(
    scheduler: Any,
    trace: ExecutionTrace,
    task: Dict[str, Any],
    status: str,
    tick: Optional[int] = None,
    final_answer: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    trace_runtime = getattr(scheduler, "trace_runtime", None)
    if trace_runtime is not None and hasattr(trace_runtime, "scheduler_trace_status"):
        return trace_runtime.scheduler_trace_status(
            scheduler=scheduler,
            trace=trace,
            task=task,
            status=status,
            tick=tick,
            final_answer=final_answer,
            extra=extra,
        )

    trace.add_status_event(
        task_id=_task_id(scheduler, task),
        status=status,
        tick=tick,
        final_answer=final_answer,
        extra=copy.deepcopy(extra) if isinstance(extra, dict) else None,
    )
    return None


def trace_step(
    scheduler: Any,
    trace: ExecutionTrace,
    task: Dict[str, Any],
    step_index: int,
    step: Dict[str, Any],
    ok: bool,
    result: Optional[Dict[str, Any]] = None,
    error: str = "",
    tick: Optional[int] = None,
) -> None:
    trace_runtime = getattr(scheduler, "trace_runtime", None)
    if trace_runtime is not None and hasattr(trace_runtime, "scheduler_trace_step"):
        return trace_runtime.scheduler_trace_step(
            scheduler=scheduler,
            trace=trace,
            task=task,
            step_index=step_index,
            step=step,
            ok=ok,
            result=result,
            error=error,
            tick=tick,
        )

    trace.add_step_event(
        task_id=_task_id(scheduler, task),
        step_index=step_index,
        step=copy.deepcopy(step),
        ok=bool(ok),
        result=copy.deepcopy(result) if isinstance(result, dict) else None,
        error=str(error or ""),
        tick=tick,
    )
    return None


def trace_replan(
    scheduler: Any,
    trace: ExecutionTrace,
    task: Dict[str, Any],
    tick: Optional[int],
    replan_result: Dict[str, Any],
) -> None:
    trace_runtime = getattr(scheduler, "trace_runtime", None)
    if trace_runtime is not None and hasattr(trace_runtime, "scheduler_trace_replan"):
        return trace_runtime.scheduler_trace_replan(
            scheduler=scheduler,
            trace=trace,
            task=task,
            tick=tick,
            replan_result=replan_result,
        )

    raw_replan_result = replan_result.get("raw_replan_result", {})
    if not isinstance(raw_replan_result, dict):
        raw_replan_result = {}

    plan = raw_replan_result.get("plan", {})
    if not isinstance(plan, dict):
        plan = {}

    meta = plan.get("meta", {})
    if not isinstance(meta, dict):
        meta = {}

    new_steps = plan.get("steps", [])
    if not isinstance(new_steps, list):
        new_steps = []

    trace.add_replan_event(
        task_id=_task_id(scheduler, task),
        failed_step_index=int(meta.get("failed_step_index", -1) or -1),
        failed_step_type=str(meta.get("failed_step_type") or ""),
        error_type=str(meta.get("error_type") or ""),
        failed_error=str(meta.get("failed_error") or ""),
        repair_mode=str(meta.get("repair_mode") or ""),
        replan_count=int(replan_result.get("replan_count", task.get("replan_count", 0)) or 0),
        max_replans=int(meta.get("max_replans", task.get("max_replans", 0)) or 0),
        new_steps=copy.deepcopy(new_steps),
        tick=tick,
    )
    return None
