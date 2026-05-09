from __future__ import annotations

from core.runtime.execution_cycle_runtime import ExecutionCycleRuntime
from core.tasks.scheduler import Scheduler


def test_scheduler_constructs_execution_cycle_runtime_boundary() -> None:
    scheduler = Scheduler()

    assert hasattr(scheduler, "execution_cycle_runtime")
    assert isinstance(scheduler.execution_cycle_runtime, ExecutionCycleRuntime)


def test_scheduler_execution_cycle_runtime_describe_is_available() -> None:
    scheduler = Scheduler()

    info = scheduler.execution_cycle_runtime.describe()

    assert info["runtime"] == "execution_cycle_runtime"