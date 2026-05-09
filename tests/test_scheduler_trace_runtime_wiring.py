from __future__ import annotations

from core.runtime.trace_runtime import TraceRuntime
from core.tasks.scheduler import Scheduler


def test_scheduler_constructs_trace_runtime_boundary() -> None:
    scheduler = Scheduler()

    assert hasattr(scheduler, "trace_runtime")
    assert isinstance(scheduler.trace_runtime, TraceRuntime)


def test_scheduler_trace_runtime_can_build_task_trace_path() -> None:
    scheduler = Scheduler()

    path = scheduler.trace_runtime.trace_file_for_task(
        {
            "task_id": "scheduler_trace_runtime_demo",
        }
    )

    assert path.name == "scheduler_trace_runtime_demo.json"
    assert "runtime_traces" in str(path)