from __future__ import annotations

from core.tools.execution_trace import ExecutionTrace
from core.tasks.scheduler import Scheduler


def test_scheduler_save_trace_redirects_through_trace_runtime() -> None:
    scheduler = Scheduler()

    task = {
        "task_id": "trace_save_redirect_demo",
    }

    trace = ExecutionTrace()

    saved = scheduler._save_trace_for_task(task, trace)

    assert saved is not None
    assert task["trace_file"].endswith("trace.json")
    assert "trace_save_redirect_demo" in task["trace_file"]