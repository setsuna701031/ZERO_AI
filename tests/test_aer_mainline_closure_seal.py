from __future__ import annotations

from pathlib import Path
from typing import Any

import cli.control_cli as control_cli
import cli.work_package_cli as work_package_cli
import core.runtime.task_runner as task_runner_module
import core.tasks.scheduler as scheduler_module
from core.runtime.runtime_route_keys import RuntimeRouteKeys


def test_aer_work_package_cli_mainline_uses_registry_and_preserves_metadata(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)

    result = work_package_cli._run_via_mainline(
        str(tmp_path),
        entrypoint="cli.work_package_cli.run",
        runner=lambda: {
            "ok": True,
            "package_id": "wp-mainline",
            "completion": {"operator_completion_marker": True},
            "evidence": {"authority_metadata": {"sealed": True}},
        },
        goal="wp-mainline",
        request={"command": "run", "package_id": "wp-mainline"},
    )

    assert calls == [RuntimeRouteKeys.CLI_WORK_PACKAGE_RUN]
    assert result["ok"] is True
    assert result["runtime_route_registry_admission"] is True
    assert result["runtime_route_key"] == RuntimeRouteKeys.CLI_WORK_PACKAGE_RUN
    assert result["completion"]["operator_completion_marker"] is True
    assert result["evidence"]["authority_metadata"]["sealed"] is True


def test_scheduler_tick_and_run_one_step_are_registry_admitted(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)

    monkeypatch.setattr(
        scheduler_module,
        "_dispatch_pipeline_tick",
        lambda self, current_tick=None: {
            "ok": True,
            "mode": "tick",
            "completion": {"scheduler_completion_marker": True},
        },
    )
    monkeypatch.setattr(
        scheduler_module,
        "_execution_pipeline_run_one_step",
        lambda self, task, current_tick=None, terminal_statuses=None: {
            "ok": True,
            "mode": "run_one_step",
            "task_id": task.get("task_id"),
            "current_tick": current_tick,
            "evidence": {"scheduler_step_evidence": True},
        },
    )

    scheduler = scheduler_module.Scheduler.__new__(scheduler_module.Scheduler)
    scheduler.workspace_dir = str(tmp_path)

    tick_result = scheduler_module.Scheduler.tick(scheduler, current_tick=3)
    step_result = scheduler_module.Scheduler.run_one_step(
        scheduler,
        task={"task_id": "task-1", "goal": "mainline step"},
        current_tick=4,
    )

    assert calls == [RuntimeRouteKeys.SCHEDULER_TICK, RuntimeRouteKeys.SCHEDULER_RUN_STEP]
    assert tick_result["runtime_route_registry_admission"] is True
    assert tick_result["completion"]["scheduler_completion_marker"] is True
    assert step_result["runtime_route_registry_admission"] is True
    assert step_result["runtime_route_key"] == RuntimeRouteKeys.SCHEDULER_RUN_STEP
    assert step_result["evidence"]["scheduler_step_evidence"] is True


def test_taskrunner_execute_owned_step_and_tick_admissions_use_registry(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)

    runner = task_runner_module.TaskRunner.__new__(task_runner_module.TaskRunner)
    runner.runtime = _Runtime(tmp_path)
    runner.step_executor = _StepExecutor()
    runner._build_taskrunner_authority_context = lambda **kwargs: {"authority_phase": "test"}

    execute_result = task_runner_module.TaskRunner.execute_owned_step(
        runner,
        {"type": "noop"},
        task={"task_id": "task-1", "goal": "noop"},
        context={},
    )

    tick_admission_result = task_runner_module.TaskRunner._run_via_runtime_native_mainline(
        runner,
        entrypoint="core.runtime.task_runner.TaskRunner.run_task_tick",
        runner=lambda: {
            "ok": True,
            "route_marker": "task-tick",
            "completion": {"taskrunner_tick_completion_marker": True},
        },
        request={"task_id": "task-2", "goal": "tick"},
        goal="tick",
    )

    assert calls == [RuntimeRouteKeys.TASK_RUNNER_EXECUTE_STEP, RuntimeRouteKeys.TASK_RUNNER_TICK]
    assert execute_result["runtime_route_registry_admission"] is True
    assert execute_result["route_marker"] == "step-executed"
    assert execute_result["authority"]["sealed"] is True
    assert tick_admission_result["runtime_route_registry_admission"] is True
    assert tick_admission_result["runtime_route_key"] == RuntimeRouteKeys.TASK_RUNNER_TICK
    assert tick_admission_result["route_marker"] == "task-tick"
    assert tick_admission_result["completion"]["taskrunner_tick_completion_marker"] is True


def test_read_only_control_surface_does_not_use_registry(monkeypatch, tmp_path: Path) -> None:
    def fail_registry_run(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("read-only/control route should not use RuntimeRouteRegistry")

    monkeypatch.setattr("core.runtime.runtime_route_registry.RuntimeRouteRegistry.run", fail_registry_run)

    api = _ControlAPI()
    exit_code = control_cli.main(["--workspace", str(tmp_path), "inspect", "task-1"], api=api)

    assert exit_code == 0
    assert api.calls == ["inspect:task-1"]


def _patch_registry_run_observer(monkeypatch):
    calls: list[str] = []

    def fake_run(self, route_key, request=None, workspace_root=None, goal="", mainline=None):
        calls.append(route_key)
        record = self.get(route_key)
        runner = record.runner_factory(request or {}, workspace_root or "workspace", goal or route_key)
        raw_result = runner()
        if not isinstance(raw_result, dict):
            return raw_result
        result = dict(raw_result)
        result.setdefault("runtime_route_registry_admission", True)
        result.setdefault("runtime_route_key", route_key)
        route = result.get("route")
        if not isinstance(route, dict):
            route = {}
        route.setdefault("runtime_route_registry_admission", True)
        route.setdefault("runtime_route_key", route_key)
        result["route"] = route
        return result

    monkeypatch.setattr("core.runtime.runtime_route_registry.RuntimeRouteRegistry.run", fake_run)
    return calls


class _Runtime:
    def __init__(self, root: Path) -> None:
        self.workspace_root = str(root)


class _StepExecutor:
    def execute_step(
        self,
        step,
        context=None,
        task=None,
        previous_result=None,
        step_index=0,
        step_count=1,
        **kwargs,
    ):
        return {
            "ok": True,
            "route_marker": "step-executed",
            "step": step,
            "authority": {"sealed": True},
            "previous_result": previous_result,
            "step_index": step_index,
            "step_count": step_count,
        }


class _ControlAPI:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def inspect_task(self, task_id: str):
        self.calls.append(f"inspect:{task_id}")
        return {"ok": True, "task_id": task_id}

    def inspect(self, task_id: str):
        return self.inspect_task(task_id)
