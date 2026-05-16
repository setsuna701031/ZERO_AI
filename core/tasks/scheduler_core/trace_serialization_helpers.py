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
    """Extract the first execution_trace list found in a nested result payload."""
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
    try:
        trace.load(trace_path)
    except Exception:
        trace.clear()
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
