from __future__ import annotations

from typing import Any


def _handle_simple_terminal_task(
    scheduler,
    task: Dict[str, Any],
    trace: ExecutionTrace,
    task_id: str,
    task_name: str,
    task_status: str,
) -> Dict[str, Any]:
    scheduler._trace_status(
        trace=trace,
        task=task,
        status=task_status,
        tick=scheduler.current_tick,
        final_answer=str(task.get("final_answer") or ""),
        extra={"action": "terminal_skip"},
    )
    scheduler._save_trace_for_task(task=task, trace=trace)
    return {
        "ok": True,
        "action": "terminal_skip",
        "tick": scheduler.current_tick,
        "task_id": task_id,
        "task_name": task_name,
        "status": task_status,
        "message": "task already terminal",
        "final_answer": task.get("final_answer", ""),
    }

