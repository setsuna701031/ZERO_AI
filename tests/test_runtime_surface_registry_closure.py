from __future__ import annotations

from pathlib import Path

import pytest

import cli.control_cli as control_cli
import cli.task_cli as task_cli
import core.runtime.task_runner as task_runner_module
import core.tasks.scheduler as scheduler_module
from core.runtime.runtime_route_keys import RuntimeRouteKeys
from core.runtime.runtime_route_registry import RuntimeRouteRegistry
pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




def test_cli_execution_route_goes_through_runtime_route_registry(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)

    result = task_cli._run_via_mainline(
        tmp_path,
        entrypoint="cli.task_cli.run",
        runner=lambda: {"ok": True, "final_answer": "ran"},
        goal="task run",
        request={"command": "run"},
    )

    assert calls == [RuntimeRouteKeys.CLI_TASK_RUN]
    assert result["ok"] is True
    assert result["final_answer"] == "ran"
    assert result["runtime_route_registry_admission"] is True


def test_scheduler_public_execution_route_goes_through_runtime_route_registry(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)
    monkeypatch.setattr(scheduler_module, "_dispatch_pipeline_tick", lambda self, current_tick=None: {"ok": True, "mode": "tick"})
    scheduler = scheduler_module.Scheduler.__new__(scheduler_module.Scheduler)
    scheduler.workspace_dir = str(tmp_path)

    result = scheduler_module.Scheduler.tick(scheduler, current_tick=7)

    assert calls == [RuntimeRouteKeys.SCHEDULER_TICK]
    assert result["ok"] is True
    assert result["mode"] == "tick"
    assert result["runtime_route_registry_admission"] is True


def test_taskrunner_public_execution_route_goes_through_runtime_route_registry(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)
    runner = task_runner_module.TaskRunner.__new__(task_runner_module.TaskRunner)
    runner.runtime = _Runtime(tmp_path)
    runner.step_executor = _StepExecutor()
    runner._build_taskrunner_authority_context = lambda **kwargs: {"authority_phase": "test"}

    result = task_runner_module.TaskRunner.execute_owned_step(
        runner,
        {"type": "noop"},
        task={"task_id": "task-1", "goal": "noop"},
        context={},
    )

    assert calls == [RuntimeRouteKeys.TASK_RUNNER_EXECUTE_STEP]
    assert result["ok"] is True
    assert result["route_marker"] == "step-executed"
    assert result["runtime_route_registry_admission"] is True


def test_read_only_control_route_does_not_use_runtime_route_registry(monkeypatch, tmp_path: Path) -> None:
    def fail_registry_run(*args, **kwargs):
        raise AssertionError("read-only route should not use registry")

    monkeypatch.setattr("core.runtime.runtime_route_registry.RuntimeRouteRegistry.run", fail_registry_run)
    api = _ControlAPI()

    exit_code = control_cli.main(["--workspace", str(tmp_path), "inspect", "task-1"], api=api)

    assert exit_code == 0
    assert api.calls == ["inspect:task-1"]


def test_surface_registry_dict_result_adds_metadata(tmp_path: Path) -> None:
    registry = RuntimeRouteRegistry()
    registry.register(
        RuntimeRouteKeys.CLI_CONTROL_SUBMIT,
        lambda request, workspace_root, goal: lambda: {"ok": True, "route": {"existing_marker": True}},
        {"entrypoint": "tests.surface.control_submit"},
    )

    result = registry.run(RuntimeRouteKeys.CLI_CONTROL_SUBMIT, {}, tmp_path, "submit")

    assert result["ok"] is True
    assert result["runtime_route_registry_admission"] is True
    assert result["route"]["existing_marker"] is True
    assert result["route"]["runtime_route_registry_admission"] is True


def test_surface_registry_non_dict_result_returns_raw_value(tmp_path: Path) -> None:
    registry = RuntimeRouteRegistry()
    registry.register(
        RuntimeRouteKeys.CLI_TASK_DRAIN,
        lambda request, workspace_root, goal: lambda: "raw-surface-result",
        {"entrypoint": "tests.surface.raw"},
    )

    result = registry.run(RuntimeRouteKeys.CLI_TASK_DRAIN, {}, tmp_path, "drain")

    assert result == "raw-surface-result"
    assert not isinstance(result, dict)


def test_surface_registry_exception_reraises(tmp_path: Path) -> None:
    registry = RuntimeRouteRegistry()

    def failing_runner():
        raise RuntimeError("surface boom")

    registry.register(
        RuntimeRouteKeys.TASK_RUNNER_RUN,
        lambda request, workspace_root, goal: failing_runner,
        {"entrypoint": "tests.surface.failure"},
    )

    with pytest.raises(RuntimeError, match="surface boom"):
        registry.run(RuntimeRouteKeys.TASK_RUNNER_RUN, {}, tmp_path, "failure")


def test_surface_default_registry_has_route_records() -> None:
    from core.runtime.runtime_route_registry import default_runtime_route_registry

    registry = default_runtime_route_registry()

    assert registry.has(RuntimeRouteKeys.CLI_TASK_RUN) is True
    assert registry.has(RuntimeRouteKeys.CLI_WORK_PACKAGE_RUN) is True
    assert registry.has(RuntimeRouteKeys.CLI_CONTROL_SUBMIT) is True
    assert registry.has(RuntimeRouteKeys.SCHEDULER_TICK) is True
    assert registry.has(RuntimeRouteKeys.SCHEDULER_RUN_STEP) is True
    assert registry.has(RuntimeRouteKeys.TASK_RUNNER_RUN) is True
    assert registry.has(RuntimeRouteKeys.TASK_RUNNER_EXECUTE_STEP) is True


def _patch_registry_run_observer(monkeypatch):
    calls = []

    def fake_run(self, route_key, request, workspace_root, goal, mainline=None):
        calls.append(route_key)
        record = self.get(route_key)
        runner = record.runner_factory(request or {}, workspace_root, goal)
        raw_result = runner()
        if not isinstance(raw_result, dict):
            return raw_result
        result = dict(raw_result)
        result.setdefault("runtime_route_registry_admission", True)
        result.setdefault("runtime_route_key", route_key)
        result.setdefault("runtime_native_mainline_canonical_entry", True)
        result.setdefault("runtime_native_mainline_compatibility_wrapper", True)
        return result

    monkeypatch.setattr("core.runtime.runtime_route_registry.RuntimeRouteRegistry.run", fake_run)
    return calls


class _Runtime:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = str(workspace_root)


class _StepExecutor:
    def execute_step(self, **kwargs):
        return {"ok": True, "route_marker": "step-executed", "step": kwargs.get("step")}


class _ControlAPI:
    def __init__(self) -> None:
        self.calls = []

    def inspect_task(self, task_id: str):
        self.calls.append(f"inspect:{task_id}")
        return {"ok": True, "task_id": task_id}
