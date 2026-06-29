from __future__ import annotations

from pathlib import Path
from typing import Any

import cli.goal_cli as goal_cli
import cli.portfolio_cli as portfolio_cli
import cli.program_cli as program_cli
import cli.work_package_cli as work_package_cli
import core.runtime.task_runner as task_runner_module
import core.tasks.scheduler as scheduler_module
from core.runtime.runtime_route_keys import RuntimeRouteKeys


def test_work_package_cli_followup_variants_are_registry_admitted(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)

    submit = work_package_cli._run_via_mainline(
        str(tmp_path),
        entrypoint="cli.work_package_cli.submit",
        runner=lambda: {"ok": True, "package_id": "wp-submit", "variant": "submit"},
        goal="wp-submit",
        request={"command": "submit", "package_id": "wp-submit"},
    )
    intake = work_package_cli._run_via_mainline(
        str(tmp_path),
        entrypoint="cli.work_package_cli.intake",
        runner=lambda: {"ok": True, "package_id": "wp-intake", "variant": "intake"},
        goal="wp-intake",
        request={"command": "intake", "package_id": "wp-intake"},
    )
    scheduler_submit = work_package_cli._run_via_mainline(
        str(tmp_path),
        entrypoint="cli.work_package_cli.scheduler_submit",
        runner=lambda: {"ok": True, "package_id": "wp-scheduler", "variant": "scheduler-submit"},
        goal="wp-scheduler",
        request={"command": "scheduler-submit", "package_id": "wp-scheduler"},
    )
    run_validation = work_package_cli._run_via_mainline(
        str(tmp_path),
        entrypoint="cli.work_package_cli.run_validation",
        runner=lambda: {"ok": True, "package_id": "wp-validation", "variant": "run-validation"},
        goal="wp-validation",
        request={"command": "run-validation", "package_id": "wp-validation"},
    )
    dispatch_request = work_package_cli._run_via_mainline(
        str(tmp_path),
        entrypoint="cli.work_package_cli.dispatch_request",
        runner=lambda: {"ok": True, "package_id": "wp-dispatch", "variant": "dispatch-request"},
        goal="wp-dispatch",
        request={"command": "dispatch-request", "package_id": "wp-dispatch"},
    )

    assert calls == [
        RuntimeRouteKeys.CLI_WORK_PACKAGE_SUBMIT,
        RuntimeRouteKeys.CLI_WORK_PACKAGE_SUBMIT,
        RuntimeRouteKeys.CLI_WORK_PACKAGE_SUBMIT,
        RuntimeRouteKeys.CLI_WORK_PACKAGE_VALIDATION,
        RuntimeRouteKeys.CLI_WORK_PACKAGE_DISPATCH_REQUEST,
    ]
    for result in (submit, intake, scheduler_submit, run_validation, dispatch_request):
        assert result["ok"] is True
        assert result["runtime_route_registry_admission"] is True
        assert result["runtime_native_mainline_canonical_entry"] is True
        assert result["package_id"].startswith("wp-")


def test_goal_portfolio_program_followup_variants_are_registry_admitted(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)

    goal_loop = goal_cli._run_via_mainline(
        tmp_path,
        entrypoint="cli.goal_cli.loop",
        runner=lambda: {"ok": True, "final_answer": "goal loop"},
        goal="goal-loop",
        request={"command": "loop", "goal_id": "goal-loop"},
    )
    portfolio_run_next = portfolio_cli._run_via_mainline(
        tmp_path,
        entrypoint="cli.portfolio_cli.run_next",
        runner=lambda: {"ok": True, "final_answer": "portfolio run-next"},
        goal="portfolio-run",
        request={"command": "run-next", "portfolio_id": "portfolio-run"},
    )
    portfolio_run_until_idle = portfolio_cli._run_via_mainline(
        tmp_path,
        entrypoint="cli.portfolio_cli.run_until_idle",
        runner=lambda: {"ok": True, "final_answer": "portfolio run-until-idle"},
        goal="portfolio-cycle",
        request={"command": "run-until-idle", "portfolio_id": "portfolio-cycle"},
    )
    program_run_next = program_cli._run_via_mainline(
        tmp_path,
        entrypoint="cli.program_cli.run_next",
        runner=lambda: {"ok": True, "final_answer": "program run-next"},
        goal="program-run",
        request={"command": "run-next", "program_id": "program-run"},
    )
    program_run_until_idle = program_cli._run_via_mainline(
        tmp_path,
        entrypoint="cli.program_cli.run_until_idle",
        runner=lambda: {"ok": True, "final_answer": "program run-until-idle"},
        goal="program-cycle",
        request={"command": "run-until-idle", "program_id": "program-cycle"},
    )

    assert calls == [
        RuntimeRouteKeys.CLI_GOAL_LOOP,
        RuntimeRouteKeys.CLI_PORTFOLIO_RUN,
        RuntimeRouteKeys.CLI_PORTFOLIO_CYCLE,
        RuntimeRouteKeys.CLI_PROGRAM_RUN,
        RuntimeRouteKeys.CLI_PROGRAM_CYCLE,
    ]
    for result in (goal_loop, portfolio_run_next, portfolio_run_until_idle, program_run_next, program_run_until_idle):
        assert result["ok"] is True
        assert result["runtime_route_registry_admission"] is True
        assert result["final_answer"]


def test_scheduler_run_one_step_variant_is_registry_admitted(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)
    monkeypatch.setattr(
        scheduler_module,
        "_completion_pipeline_run_one_step_v16",
        lambda self, args, kwargs, **deps: deps["base_run_one_step"](self, *args, **kwargs),
    )
    monkeypatch.setattr(scheduler_module, "_zero_scheduler_update_step_progress", lambda task, result: None)
    monkeypatch.setattr(scheduler_module, "_zero_scheduler_complete_operator", lambda self, task, result, *, outcome="complete": None)
    monkeypatch.setattr(
        scheduler_module,
        "_execution_pipeline_run_one_step",
        lambda self, task, current_tick=None, terminal_statuses=None: {
            "ok": True,
            "mode": "run_one_step",
            "task_id": task.get("task_id"),
            "current_tick": current_tick,
        },
    )
    scheduler = scheduler_module.Scheduler.__new__(scheduler_module.Scheduler)
    scheduler.workspace_dir = str(tmp_path)

    result = scheduler_module.Scheduler.run_one_step(
        scheduler,
        task={"task_id": "task-1", "goal": "one step"},
        current_tick=11,
    )

    assert calls == [RuntimeRouteKeys.SCHEDULER_RUN_STEP]
    assert result["ok"] is True
    assert result["mode"] == "run_one_step"
    assert result["task_id"] == "task-1"
    assert result["runtime_route_registry_admission"] is True


def test_scheduler_submit_variants_are_registry_admitted(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)
    scheduler = scheduler_module.Scheduler.__new__(scheduler_module.Scheduler)
    scheduler.workspace_dir = str(tmp_path)
    scheduler._pre_enqueue_repair_fingerprint_gate = lambda goal, kwargs: None
    scheduler._create_task_record = lambda **kwargs: {
        "ok": True,
        "task_name": "created-task",
        "message": "created",
        "goal": kwargs.get("goal"),
    }
    scheduler.submit_existing_task = lambda task_id, _runtime_native_mainline_delegate=False: {
        "ok": True,
        "task_id": task_id,
        "task_name": task_id,
        "status": "queued",
        "message": "task submitted",
    }

    submit_task = scheduler_module.Scheduler.submit_task(scheduler, "created goal")
    scheduler.submit_existing_task = scheduler_module.Scheduler.submit_existing_task.__get__(scheduler, scheduler_module.Scheduler)
    submit_existing_empty = scheduler_module.Scheduler.submit_existing_task(scheduler, "")

    assert calls == [RuntimeRouteKeys.SCHEDULER_SUBMIT_TASK, RuntimeRouteKeys.SCHEDULER_SUBMIT_TASK]
    assert submit_task["ok"] is True
    assert submit_task["submit_result"]["task_id"] == "created-task"
    assert submit_task["runtime_route_registry_admission"] is True
    assert submit_existing_empty["ok"] is False
    assert submit_existing_empty["error"] == "task_id is empty"
    assert submit_existing_empty["runtime_route_registry_admission"] is True


def test_taskrunner_alias_variants_are_registry_admitted(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)
    runner = _make_taskrunner(tmp_path)

    run_one_step = task_runner_module.TaskRunner.run_one_step(
        runner,
        {"task_id": "task-one-step", "goal": "already done"},
        current_tick=1,
    )
    run_task = task_runner_module.TaskRunner.run_task(
        runner,
        {"task_id": "task-run", "goal": "already done"},
        current_tick=2,
    )
    run_one_tick = task_runner_module.TaskRunner.run_one_tick(
        runner,
        {"task_id": "task-one-tick", "goal": "already done"},
        current_tick=3,
    )

    assert calls == [
        RuntimeRouteKeys.TASK_RUNNER_TICK,
        RuntimeRouteKeys.TASK_RUNNER_TICK,
        RuntimeRouteKeys.TASK_RUNNER_TICK,
    ]
    for result, task_id in (
        (run_one_step, "task-one-step"),
        (run_task, "task-run"),
        (run_one_tick, "task-one-tick"),
    ):
        assert result["ok"] is True
        assert result["action"] == "already_finished"
        assert result["task"]["task_id"] == task_id
        assert result["runtime_route_registry_admission"] is True


def test_taskrunner_execute_owned_steps_variant_is_registry_admitted(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)
    runner = _make_taskrunner(tmp_path)
    runner.step_executor = _BatchStepExecutor()
    monkeypatch.setattr(
        task_runner_module,
        "delegate_taskrunner_execution_capability",
        lambda *args, **kwargs: {"capability": "taskrunner-batch"},
    )

    result = task_runner_module.TaskRunner.execute_owned_steps(
        runner,
        [{"type": "noop"}, {"type": "noop"}],
        task={"task_id": "batch-task", "goal": "batch"},
        context={"source": "test"},
    )

    assert calls == [RuntimeRouteKeys.TASK_RUNNER_EXECUTE_STEPS]
    assert result["ok"] is True
    assert result["route_marker"] == "batch-executed"
    assert result["count"] == 2
    assert result["runtime_route_registry_admission"] is True


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
        route = result.get("route")
        if isinstance(route, dict):
            route.setdefault("runtime_route_registry_admission", True)
            route.setdefault("runtime_route_key", route_key)
        return result

    monkeypatch.setattr("core.runtime.runtime_route_registry.RuntimeRouteRegistry.run", fake_run)
    return calls


def _make_taskrunner(tmp_path: Path):
    runner = task_runner_module.TaskRunner.__new__(task_runner_module.TaskRunner)
    runner.runtime = _TaskRuntime(tmp_path)
    runner.step_executor = _BatchStepExecutor()
    runner._ensure_execution_trace_defaults = lambda task, state: None
    runner._safe_int = lambda value, default=0: int(value or default)
    runner._finalize_public_result = lambda result: result
    return runner


class _TaskRuntime:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = str(workspace_root)

    def load_runtime_state(self, task):
        return {
            "status": "finished",
            "final_answer": f"finished {task.get('task_id')}",
            "execution_trace": [{"ok": True}],
        }


class _BatchStepExecutor:
    def execute_steps(self, steps, **kwargs):
        return {
            "ok": True,
            "route_marker": "batch-executed",
            "count": len(steps),
            "steps": steps,
            "task": kwargs.get("task"),
            "context": kwargs.get("context"),
        }
