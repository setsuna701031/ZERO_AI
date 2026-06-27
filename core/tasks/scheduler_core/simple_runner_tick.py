from __future__ import annotations

from typing import Any, Dict, Optional

from core.tasks.scheduler_core.simple_runner_terminal import _handle_simple_terminal_task
from core.tasks.scheduler_core.simple_runner_blocked import _handle_simple_blocked_task
from core.tasks.scheduler_core.simple_runner_finished import _handle_simple_finished_task
from core.tasks.scheduler_core.simple_runner_invalid import _handle_simple_invalid_step
from core.tasks.scheduler_core.simple_runner_step_exception import _handle_simple_step_exception
from core.tasks.scheduler_core.simple_runner_step_success import _handle_simple_step_success


def _run_simple_task_tick(
    scheduler,
    task: Dict[str, Any],
    current_tick: Optional[int] = None,
) -> Dict[str, Any]:
    if current_tick is not None:
        scheduler.current_tick = int(current_tick)

    task = scheduler._hydrate_task_from_workspace(task)

    task_id = scheduler._extract_task_id(task)
    task_name = str(task.get("task_name") or task_id or "unknown_task")
    task_status = str(task.get("status") or "").strip().lower()
    trace = scheduler._load_trace_for_task(task)

    if task_status in getattr(scheduler, "TERMINAL_STATUSES", set()):
        return _handle_simple_terminal_task(
            scheduler=scheduler,
            task=task,
            trace=trace,
            task_id=task_id,
            task_name=task_name,
            task_status=task_status,
        )

    deps_ready, blocked_reason = scheduler._task_dependencies_satisfied(task)
    if not deps_ready:
        return _handle_simple_blocked_task(
            scheduler=scheduler,
            task=task,
            trace=trace,
            task_id=task_id,
            task_name=task_name,
            blocked_reason=blocked_reason,
        )

    steps, current_step_index, execution_log, results, step_results, last_step_result = (
        scheduler._load_simple_task_state(task)
    )

    if current_step_index >= len(steps):
        return _handle_simple_finished_task(
            scheduler=scheduler,
            task=task,
            trace=trace,
            task_id=task_id,
            task_name=task_name,
            current_step_index=current_step_index,
            steps=steps,
            execution_log=execution_log,
            results=results,
            step_results=step_results,
            last_step_result=last_step_result,
        )

    step = steps[current_step_index]
    if not isinstance(step, dict):
        return _handle_simple_invalid_step(
            scheduler=scheduler,
            task=task,
            trace=trace,
            task_id=task_id,
            task_name=task_name,
            results=results,
            step_results=step_results,
            last_step_result=last_step_result,
        )

    try:
        step_result = scheduler._execute_simple_step(task=task, step=step)
    except Exception as e:
        return _handle_simple_step_exception(
            scheduler=scheduler,
            task=task,
            trace=trace,
            task_id=task_id,
            task_name=task_name,
            current_step_index=current_step_index,
            step=step,
            error=e,
            execution_log=execution_log,
            results=results,
            step_results=step_results,
            last_step_result=last_step_result,
        )

    return _handle_simple_step_success(
        scheduler=scheduler,
        task=task,
        trace=trace,
        task_id=task_id,
        task_name=task_name,
        current_step_index=current_step_index,
        step=step,
        step_result=step_result,
        steps=steps,
        execution_log=execution_log,
        results=results,
        step_results=step_results,
        last_step_result=last_step_result,
    )

