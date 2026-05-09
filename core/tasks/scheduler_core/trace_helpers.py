from __future__ import annotations

import copy
import os
from typing import Any, Dict, List, Optional

from core.tools.execution_trace import ExecutionTrace


def _task_id(scheduler: Any, task: Dict[str, Any]) -> str:
    try:
        return str(scheduler._extract_task_id(task) or "unknown_task")
    except Exception:
        return "unknown_task"


def extract_execution_trace_from_payload(payload: Any) -> List[Dict[str, Any]]:
    """Extract the first execution_trace list found in a nested result payload.

    This helper is intentionally pure and scheduler-independent so the
    scheduler can keep only a thin compatibility wrapper.
    """
    if isinstance(payload, dict):
        direct = payload.get("execution_trace")
        if isinstance(direct, list):
            return [copy.deepcopy(item) for item in direct if isinstance(item, dict)]

        for key in ("result", "raw_result", "runner_result", "last_result", "task"):
            nested = payload.get(key)
            extracted = extract_execution_trace_from_payload(nested)
            if extracted:
                return extracted

    if isinstance(payload, list):
        for item in payload:
            extracted = extract_execution_trace_from_payload(item)
            if extracted:
                return extracted

    return []


def promote_execution_trace_in_executed_results(
    executed_results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Promote nested execution_trace payloads to each executed-result row."""
    promoted: List[Dict[str, Any]] = []

    for item in executed_results:
        if not isinstance(item, dict):
            promoted.append(item)
            continue

        normalized = copy.deepcopy(item)
        trace = extract_execution_trace_from_payload(normalized)
        if trace:
            normalized["execution_trace"] = trace

            result_payload = normalized.get("result")
            if isinstance(result_payload, dict) and "execution_trace" not in result_payload:
                result_payload["execution_trace"] = copy.deepcopy(trace)

        promoted.append(normalized)

    return promoted


def get_trace_file_for_task(scheduler: Any, task: Dict[str, Any]) -> str:
    trace_runtime = getattr(scheduler, "trace_runtime", None)
    if trace_runtime is not None and hasattr(trace_runtime, "scheduler_trace_file_for_task"):
        return trace_runtime.scheduler_trace_file_for_task(
            task=task,
            tasks_root=scheduler.tasks_root,
            task_id=_task_id(scheduler, task),
        )

    if not isinstance(task, dict):
        return os.path.join(scheduler.tasks_root, "unknown_task", "trace.json")

    task_dir = str(task.get("task_dir") or "").strip()
    if not task_dir:
        task_dir = os.path.join(scheduler.tasks_root, _task_id(scheduler, task))

    os.makedirs(task_dir, exist_ok=True)

    trace_file = str(task.get("trace_file") or "").strip()
    if trace_file:
        return trace_file

    return os.path.join(task_dir, "trace.json")


def load_trace_for_task(scheduler: Any, task: Dict[str, Any]) -> ExecutionTrace:
    trace_runtime = getattr(scheduler, "trace_runtime", None)
    if trace_runtime is not None and hasattr(trace_runtime, "load_scheduler_trace_for_task"):
        return trace_runtime.load_scheduler_trace_for_task(
            task=task,
            tasks_root=scheduler.tasks_root,
            task_id=_task_id(scheduler, task),
        )

    trace_path = get_trace_file_for_task(scheduler=scheduler, task=task)
    trace = ExecutionTrace(trace_file=trace_path)
    trace.load(trace_path)
    task["trace_file"] = trace_path
    return trace


def save_trace_for_task(scheduler: Any, task: Dict[str, Any], trace: ExecutionTrace) -> Optional[str]:
    trace_runtime = getattr(scheduler, "trace_runtime", None)
    if trace_runtime is not None and hasattr(trace_runtime, "save_scheduler_trace_for_task"):
        return trace_runtime.save_scheduler_trace_for_task(
            task=task,
            trace=trace,
            tasks_root=scheduler.tasks_root,
            task_id=_task_id(scheduler, task),
        )

    trace_path = get_trace_file_for_task(scheduler=scheduler, task=task)
    saved = trace.save(trace_path)
    task["trace_file"] = trace_path
    return saved


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
