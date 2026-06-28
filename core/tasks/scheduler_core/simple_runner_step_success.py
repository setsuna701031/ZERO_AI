from __future__ import annotations

from typing import Any, Dict, List

from core.tools.execution_trace import ExecutionTrace
from core.tasks.scheduler_core.simple_runner_failure_signal import _extract_simple_step_failure_signal
from core.tasks.scheduler_core.simple_runner_result_helpers import (
    _build_simple_success_step_result,
    _sync_simple_success_step_collections,
)
from core.tasks.scheduler_core.simple_runner_state_mutation_helpers import (
    _apply_simple_queued_state,
    _apply_simple_step_collections_to_task,
    _apply_simple_success_advance,
    _apply_simple_terminal_finished_state,
)
from core.tasks.scheduler_core.simple_runner_step_blocked_result import _handle_simple_step_blocked_or_failed_result
from core.tasks.scheduler_core.trace_helpers import trace_step


def _handle_simple_step_success(
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
) -> Dict[str, Any]:
    failure_signal = _extract_simple_step_failure_signal(step_result)
    if failure_signal.get("failed") or failure_signal.get("blocked"):
        return _handle_simple_step_blocked_or_failed_result(
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
            failure_signal=failure_signal,
        )

    normalized_step_result = _build_simple_success_step_result(
        current_step_index,
        step,
        step_result,
    )
    step_results, last_step_result = _sync_simple_success_step_collections(
        tick=scheduler.current_tick,
        current_step_index=current_step_index,
        step=step,
        step_result=step_result,
        execution_log=execution_log,
        results=results,
        normalized_step_result=normalized_step_result,
    )

    _apply_simple_step_collections_to_task(
        task,
        execution_log=execution_log,
        results=results,
        step_results=step_results,
        last_step_result=last_step_result,
    )
    _apply_simple_success_advance(scheduler, task, current_step_index)

    trace_step(
        scheduler=scheduler,
        trace=trace,
        task=task,
        step_index=current_step_index,
        step=step,
        ok=True,
        result=step_result,
        error="",
        tick=scheduler.current_tick,
    )

    if task["current_step_index"] >= len(steps):
        final_answer = scheduler._build_simple_final_answer(
            [x.get("result", x) if isinstance(x, dict) else x for x in results]
        )
        _apply_simple_terminal_finished_state(scheduler, task, final_answer)

        scheduler._trace_status(
            trace=trace,
            task=task,
            status="finished",
            tick=scheduler.current_tick,
            final_answer=final_answer,
            extra={
                "action": "simple_task_finished",
                "current_step_index": task["current_step_index"],
                "steps_total": len(steps),
            },
        )
        scheduler._save_trace_for_task(task=task, trace=trace)

        return {
            "ok": True,
            "action": "simple_task_finished",
            "tick": scheduler.current_tick,
            "task_id": task_id,
            "task_name": task_name,
            "status": "finished",
            "message": "task finished",
            "final_answer": final_answer,
            "execution_log": execution_log,
            "results": results,
            "step_results": step_results,
            "last_step_result": last_step_result,
            "current_step_index": task["current_step_index"],
            "step_count": len(steps),
            "steps_total": len(steps),
            "last_run_tick": scheduler.current_tick,
            "finished_tick": scheduler.current_tick,
        }

    _apply_simple_queued_state(scheduler, task)

    scheduler._trace_status(
        trace=trace,
        task=task,
        status="queued",
        tick=scheduler.current_tick,
        final_answer="",
        extra={
            "action": "simple_step_executed",
            "current_step_index": task["current_step_index"],
            "steps_total": len(steps),
        },
    )
    scheduler._save_trace_for_task(task=task, trace=trace)

    return {
        "ok": True,
        "action": "simple_step_executed",
        "tick": scheduler.current_tick,
        "task_id": task_id,
        "task_name": task_name,
        "status": "queued",
        "message": "step executed, waiting next tick",
        "final_answer": "",
        "execution_log": execution_log,
        "results": results,
        "step_results": step_results,
        "last_step_result": last_step_result,
        "current_step_index": task["current_step_index"],
        "step_count": len(steps),
        "steps_total": len(steps),
        "last_run_tick": scheduler.current_tick,
    }



