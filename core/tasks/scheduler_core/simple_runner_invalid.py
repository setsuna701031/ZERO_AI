from __future__ import annotations

from typing import Any, Dict, List

from core.tools.execution_trace import ExecutionTrace
from core.tasks.scheduler_core.simple_runner_state_mutation_helpers import (
    _apply_simple_invalid_step_failure_state,
)


def _handle_simple_invalid_step(
    scheduler,
    task: Dict[str, Any],
    trace: ExecutionTrace,
    task_id: str,
    task_name: str,
    results: List[Dict[str, Any]],
    step_results: List[Dict[str, Any]],
    last_step_result: Any,
) -> Dict[str, Any]:
    _apply_simple_invalid_step_failure_state(
        scheduler,
        task,
        results=results,
        step_results=step_results,
        last_step_result=last_step_result,
    )

    scheduler._trace_status(
        trace=trace,
        task=task,
        status="failed",
        tick=scheduler.current_tick,
        final_answer="",
        extra={
            "action": "simple_invalid_step",
            "error": "invalid step type",
        },
    )
    scheduler._save_trace_for_task(task=task, trace=trace)

    return {
        "ok": False,
        "action": "simple_invalid_step",
        "tick": scheduler.current_tick,
        "task_id": task_id,
        "task_name": task_name,
        "status": "failed",
        "message": "invalid step type",
        "error": "invalid step type",
    }

