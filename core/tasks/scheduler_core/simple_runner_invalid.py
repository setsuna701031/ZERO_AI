from __future__ import annotations

from typing import Any


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
    project_runtime_status(task, "failed", owner="core/tasks/scheduler_core/simple_runner_helpers.py")
    task["last_error"] = "invalid step type"
    task["failure_message"] = "invalid step type"
    task["last_failure_tick"] = scheduler.current_tick
    task["last_run_tick"] = scheduler.current_tick
    task["results"] = results
    task["step_results"] = step_results
    task["last_step_result"] = last_step_result
    task["history"] = scheduler._append_history(task.get("history"), "failed")

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

