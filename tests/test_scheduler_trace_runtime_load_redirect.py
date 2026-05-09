from __future__ import annotations

from core.tools.execution_trace import ExecutionTrace
from core.tasks.scheduler import Scheduler


def test_scheduler_load_trace_redirects_through_trace_runtime() -> None:
    scheduler = Scheduler()

    task = {
        "task_id": "trace_load_redirect_demo",
    }

    trace = scheduler._load_trace_for_task(task)

    assert isinstance(trace, ExecutionTrace)
    assert task["trace_file"].endswith("trace.json")
    assert "trace_load_redirect_demo" in task["trace_file"]