from __future__ import annotations

from typing import Any


def _handle_simple_blocked_task(
    scheduler,
    task: Dict[str, Any],
    trace: ExecutionTrace,
    task_id: str,
    task_name: str,
    blocked_reason: str,
) -> Dict[str, Any]:
    blocked_status = getattr(scheduler, "STATUS_BLOCKED", "blocked")
    project_runtime_status(task, blocked_status, owner="core/tasks/scheduler_core/simple_runner_helpers.py")
    task["blocked_reason"] = blocked_reason
    task["history"] = scheduler._append_history(task.get("history"), blocked_status)

    scheduler._trace_status(
        trace=trace,
        task=task,
        status=blocked_status,
        tick=scheduler.current_tick,
        final_answer="",
        extra={
            "action": "blocked_by_dependencies",
            "blocked_reason": blocked_reason,
        },
    )
    scheduler._save_trace_for_task(task=task, trace=trace)

    return {
        "ok": False,
        "action": "blocked_by_dependencies",
        "tick": scheduler.current_tick,
        "task_id": task_id,
        "task_name": task_name,
        "status": blocked_status,
        "blocked_reason": blocked_reason,
        "error": blocked_reason,
    }

