from __future__ import annotations

import copy
import os
from typing import Any, Dict, Optional

from core.tools.execution_trace import ExecutionTrace


def get_trace_file_for_task(scheduler: Any, task: Dict[str, Any]) -> str:
    if not isinstance(task, dict):
        return os.path.join(scheduler.tasks_root, "unknown_task", "trace.json")

    task_dir = str(task.get("task_dir") or "").strip()
    if not task_dir:
        task_id = scheduler._extract_task_id(task) or "unknown_task"
        task_dir = os.path.join(scheduler.tasks_root, task_id)

    os.makedirs(task_dir, exist_ok=True)

    trace_file = str(task.get("trace_file") or "").strip()
    if trace_file:
        return trace_file

    return os.path.join(task_dir, "trace.json")


def load_trace_for_task(scheduler: Any, task: Dict[str, Any]) -> ExecutionTrace:
    trace_path = get_trace_file_for_task(scheduler=scheduler, task=task)
    trace = ExecutionTrace(trace_file=trace_path)
    trace.load(trace_path)
    task["trace_file"] = trace_path
    return trace


def save_trace_for_task(scheduler: Any, task: Dict[str, Any], trace: ExecutionTrace) -> Optional[str]:
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
    trace.add_summary_event(
        task_id=scheduler._extract_task_id(task),
        summary=summary,
        tick=tick,
        extra=copy.deepcopy(extra) if isinstance(extra, dict) else None,
    )


def trace_status(
    scheduler: Any,
    trace: ExecutionTrace,
    task: Dict[str, Any],
    status: str,
    tick: Optional[int] = None,
    final_answer: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    trace.add_status_event(
        task_id=scheduler._extract_task_id(task),
        status=status,
        tick=tick,
        final_answer=final_answer,
        extra=copy.deepcopy(extra) if isinstance(extra, dict) else None,
    )


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
    trace.add_step_event(
        task_id=scheduler._extract_task_id(task),
        step_index=step_index,
        step=copy.deepcopy(step),
        ok=bool(ok),
        result=copy.deepcopy(result) if isinstance(result, dict) else None,
        error=str(error or ""),
        tick=tick,
    )


def trace_replan(
    scheduler: Any,
    trace: ExecutionTrace,
    task: Dict[str, Any],
    tick: Optional[int],
    replan_result: Dict[str, Any],
) -> None:
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
        task_id=scheduler._extract_task_id(task),
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
