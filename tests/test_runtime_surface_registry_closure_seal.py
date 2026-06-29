from __future__ import annotations

from pathlib import Path

import cli.control_cli as control_cli
import cli.goal_cli as goal_cli
import cli.portfolio_cli as portfolio_cli
import cli.program_cli as program_cli
import cli.task_cli as task_cli
import cli.work_package_cli as work_package_cli
import core.agent.agent_loop as agent_loop_module
import core.runtime.task_runner as task_runner_module
import core.tasks.scheduler as scheduler_module
from core.agent.agent_loop import AgentLoop
from core.runtime.runtime_route_keys import RuntimeRouteKeys


def test_agent_loop_wave1_and_wave2_entries_are_registry_admitted(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)
    monkeypatch.setattr(agent_loop_module, "_zero_v823_run_persistent_runtime_orchestrator", _persistent_runner)
    monkeypatch.setattr(agent_loop_module, "_zero_v823_should_route_persistent_runtime", lambda task, context: True)
    monkeypatch.setattr(agent_loop_module, "_zero_v823_agent_persistent_runtime_candidate", lambda text: True)
    monkeypatch.setattr(agent_loop_module, "_zero_v824_agent_planner_dispatch_candidate", lambda text: False)
    monkeypatch.setattr(agent_loop_module, "_zero_v827_run_planner_owned_code_chain_bridge", _planner_owned_bridge)
    loop = AgentLoop(repo_root=str(tmp_path), workspace_dir=str(tmp_path / "workspace"))

    wave1 = agent_loop_module._zero_v823_agent_try_persistent_runtime_route(loop, "persistent runtime seal")
    monkeypatch.setattr(agent_loop_module, "_zero_v823_agent_persistent_runtime_candidate", lambda text: False)
    wave2 = agent_loop_module._zero_v827_agent_try_planner_owned_code_chain(loop, "planner-owned seal")

    assert calls == [RuntimeRouteKeys.PERSISTENT_RUNTIME, RuntimeRouteKeys.PLANNER_OWNED_CODE_CHAIN]
    assert wave1["persistent_runtime_orchestrator_payload"]["runtime_route_registry_admission"] is True
    assert wave1["agent_loop_persistent_runtime_route"] is True
    assert wave2["runtime_route_registry_admission"] is True
    assert wave2["mode"] == "code_chain_controlled_self_edit_bridge"


def test_cli_execution_surfaces_are_registry_admitted(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)

    task_run = task_cli._run_via_mainline(
        tmp_path,
        entrypoint="cli.task_cli.run",
        runner=lambda: {"ok": True, "final_answer": "task run"},
        goal="task run",
        request={"command": "run"},
    )
    task_drain = task_cli._run_via_mainline(
        tmp_path,
        entrypoint="cli.task_cli.drain",
        runner=lambda: {"ok": True, "final_answer": "task drain"},
        goal="task drain",
        request={"command": "drain"},
    )
    work_package_run = work_package_cli._run_via_mainline(
        str(tmp_path),
        entrypoint="cli.work_package_cli.run",
        runner=lambda: {"ok": True, "final_answer": "work package run"},
        goal="wp-1",
        request={"command": "run", "package_id": "wp-1"},
    )
    goal_run = goal_cli._run_via_mainline(
        tmp_path,
        entrypoint="cli.goal_cli.run",
        runner=lambda: {"ok": True, "final_answer": "goal run"},
        goal="goal-1",
        request={"command": "run", "goal_id": "goal-1"},
    )
    portfolio_cycle = portfolio_cli._run_via_mainline(
        tmp_path,
        entrypoint="cli.portfolio_cli.cycle",
        runner=lambda: {"ok": True, "final_answer": "portfolio cycle"},
        goal="portfolio-1",
        request={"command": "cycle", "portfolio_id": "portfolio-1"},
    )
    program_cycle = program_cli._run_via_mainline(
        tmp_path,
        entrypoint="cli.program_cli.cycle",
        runner=lambda: {"ok": True, "final_answer": "program cycle"},
        goal="program-1",
        request={"command": "cycle", "program_id": "program-1"},
    )

    assert calls == [
        RuntimeRouteKeys.CLI_TASK_RUN,
        RuntimeRouteKeys.CLI_TASK_DRAIN,
        RuntimeRouteKeys.CLI_WORK_PACKAGE_RUN,
        RuntimeRouteKeys.CLI_GOAL_RUN,
        RuntimeRouteKeys.CLI_PORTFOLIO_CYCLE,
        RuntimeRouteKeys.CLI_PROGRAM_CYCLE,
    ]
    for result in (task_run, task_drain, work_package_run, goal_run, portfolio_cycle, program_cycle):
        assert result["ok"] is True
        assert result["runtime_route_registry_admission"] is True
        assert result["final_answer"]


def test_control_submit_is_registry_admitted(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)
    args = type("Args", (), {"workspace": str(tmp_path)})()

    result = control_cli._run_via_mainline(
        args,
        entrypoint="cli.control_cli.submit",
        runner=lambda: {"ok": True, "task_id": "task-1"},
        goal="submit task",
        request={"instruction": "submit task"},
    )

    assert calls == [RuntimeRouteKeys.CLI_CONTROL_SUBMIT]
    assert result["ok"] is True
    assert result["task_id"] == "task-1"
    assert result["runtime_route_registry_admission"] is True


def test_scheduler_tick_is_registry_admitted(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)
    monkeypatch.setattr(scheduler_module, "_dispatch_pipeline_tick", lambda self, current_tick=None: {"ok": True, "mode": "tick"})
    scheduler = scheduler_module.Scheduler.__new__(scheduler_module.Scheduler)
    scheduler.workspace_dir = str(tmp_path)
    scheduler.cleanup_task_queue_hygiene = lambda **kwargs: None

    result = scheduler_module.Scheduler.tick(scheduler, current_tick=3)

    assert calls == [RuntimeRouteKeys.SCHEDULER_TICK]
    assert result["ok"] is True
    assert result["mode"] == "tick"
    assert result["runtime_route_registry_admission"] is True


def test_taskrunner_run_and_tick_are_registry_admitted(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)
    runner = task_runner_module.TaskRunner.__new__(task_runner_module.TaskRunner)
    runner.runtime = _TaskRuntime(tmp_path)
    runner._ensure_execution_trace_defaults = lambda task, state: None
    runner._safe_int = lambda value, default=0: int(value or default)
    runner._finalize_public_result = lambda result: result

    run_result = task_runner_module.TaskRunner.run(
        runner,
        {"task_id": "task-1", "goal": "already done"},
        current_tick=1,
    )
    tick_result = task_runner_module.TaskRunner.run_task_tick(
        runner,
        {"task_id": "task-2", "goal": "already done"},
        current_tick=2,
    )

    assert calls == [RuntimeRouteKeys.TASK_RUNNER_TICK, RuntimeRouteKeys.TASK_RUNNER_TICK]
    for result in (run_result, tick_result):
        assert result["ok"] is True
        assert result["action"] == "already_finished"
        assert result["runtime_route_registry_admission"] is True


def test_read_only_status_list_inspect_cancel_do_not_trigger_registry(monkeypatch, tmp_path: Path) -> None:
    def fail_registry_run(*args, **kwargs):
        raise AssertionError("control/read-only route should not use registry")

    monkeypatch.setattr("core.runtime.runtime_route_registry.RuntimeRouteRegistry.run", fail_registry_run)
    api = _ControlAPI()

    assert control_cli.main(["--workspace", str(tmp_path), "inspect", "task-1"], api=api) == 0
    assert control_cli.main(["--workspace", str(tmp_path), "list", "--limit", "2"], api=api) == 0
    assert control_cli.main(["--workspace", str(tmp_path), "cancel", "task-1"], api=api) == 0
    assert api.calls == ["inspect:task-1", "list:2", "cancel:task-1"]


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


def _persistent_runner(**kwargs):
    return {
        "ok": True,
        "persistent_runtime_orchestrator": {
            "ok": True,
            "status": "finished",
            "session_id": "session-1",
            "cycle_count": 1,
            "closure_count": 1,
        },
    }


def _planner_owned_bridge(**kwargs):
    return {
        "ok": False,
        "mode": "code_chain_controlled_self_edit_bridge",
        "planner_owned_intent_routing": True,
    }


class _TaskRuntime:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = str(workspace_root)

    def load_runtime_state(self, task):
        return {
            "status": "finished",
            "final_answer": f"finished {task.get('task_id')}",
            "execution_trace": [{"ok": True}],
        }


class _ControlAPI:
    def __init__(self) -> None:
        self.calls = []

    def inspect_task(self, task_id: str):
        self.calls.append(f"inspect:{task_id}")
        return {"ok": True, "task_id": task_id}

    def list_recent_tasks(self, limit: int):
        self.calls.append(f"list:{limit}")
        return {"ok": True, "tasks": []}

    def request_cancel(self, task_id: str):
        self.calls.append(f"cancel:{task_id}")
        return {"ok": True, "task_id": task_id, "cancel_requested": True}
