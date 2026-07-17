from __future__ import annotations

from typing import Any, Dict, List

from core.tools.execution_trace import ExecutionTrace
from core.tasks.scheduler_core.simple_runner_state_mutation_helpers import (
    _apply_simple_finished_task_state,
)


def _handle_simple_finished_task(
    scheduler,
    task: Dict[str, Any],
    trace: ExecutionTrace,
    task_id: str,
    task_name: str,
    current_step_index: int,
    steps: List[Dict[str, Any]],
    execution_log: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    step_results: List[Dict[str, Any]],
    last_step_result: Any,
) -> Dict[str, Any]:
    final_answer = str(task.get("final_answer") or scheduler._build_simple_final_answer(results))
    _apply_simple_finished_task_state(
        scheduler,
        task,
        final_answer=final_answer,
        results=results,
        step_results=step_results,
        last_step_result=last_step_result,
    )

    scheduler._trace_status(
        trace=trace,
        task=task,
        status="finished",
        tick=scheduler.current_tick,
        final_answer=task["final_answer"],
        extra={
            "action": "simple_task_finished",
            "current_step_index": current_step_index,
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
        "final_answer": task["final_answer"],
        "execution_log": execution_log,
        "results": results,
        "step_results": step_results,
        "last_step_result": last_step_result,
        "current_step_index": current_step_index,
        "step_count": len(steps),
        "steps_total": len(steps),
        "last_run_tick": scheduler.current_tick,
        "finished_tick": scheduler.current_tick,
    }

