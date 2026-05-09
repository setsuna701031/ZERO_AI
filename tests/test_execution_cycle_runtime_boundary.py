from core.runtime.execution_cycle_runtime import (
    ExecutionCycleRuntime,
    build_execution_cycle_runtime,
)


def test_build_execution_cycle_runtime() -> None:
    runtime = build_execution_cycle_runtime()

    assert isinstance(runtime, ExecutionCycleRuntime)


def test_execution_cycle_runtime_describe() -> None:
    runtime = build_execution_cycle_runtime()

    info = runtime.describe()

    assert info["runtime"] == "execution_cycle_runtime"
    assert info["phase"] == "phase6_boundary_only"