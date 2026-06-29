from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from core.runtime.runtime_native_mainline import RuntimeNativeMainline
from core.runtime.runtime_route_keys import RuntimeRouteKeys


CompatibilityRunner = Callable[[], Any]
RuntimeRouteRunnerFactory = Callable[[dict[str, Any], str | Path, str], CompatibilityRunner]


@dataclass(frozen=True)
class RuntimeRouteRecord:
    route_key: str
    runner_factory: RuntimeRouteRunnerFactory
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeRouteRegistry:
    def __init__(self) -> None:
        self._routes: dict[str, RuntimeRouteRecord] = {}

    def register(
        self,
        route_key: str,
        runner_factory: RuntimeRouteRunnerFactory,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeRouteRecord:
        key = _normalize_route_key(route_key)
        if not callable(runner_factory):
            raise TypeError("runtime_route_runner_factory_must_be_callable")
        record = RuntimeRouteRecord(
            route_key=key,
            runner_factory=runner_factory,
            metadata=copy.deepcopy(metadata or {}),
        )
        self._routes[key] = record
        return record

    def has(self, route_key: str) -> bool:
        return _normalize_route_key(route_key) in self._routes

    def get(self, route_key: str) -> RuntimeRouteRecord:
        key = _normalize_route_key(route_key)
        try:
            return self._routes[key]
        except KeyError as exc:
            raise KeyError(f"runtime_route_not_registered:{key}") from exc

    def run(
        self,
        route_key: str,
        request: dict[str, Any] | None,
        workspace_root: str | Path,
        goal: str,
        mainline: RuntimeNativeMainline | None = None,
    ) -> Any:
        record = self.get(route_key)
        payload = copy.deepcopy(request) if isinstance(request, dict) else {}
        root = workspace_root or "workspace"
        run_goal = str(goal or payload.get("goal") or payload.get("summary") or record.route_key).strip()
        runner = record.runner_factory(copy.deepcopy(payload), root, run_goal)
        if not callable(runner):
            raise TypeError("runtime_route_runner_factory_returned_non_callable")

        entrypoint = str(record.metadata.get("entrypoint") or record.route_key)
        admission_metadata = {
            "runtime_route_registry_admission": True,
            "runtime_route_key": record.route_key,
            **copy.deepcopy(record.metadata),
        }
        runtime_mainline = mainline or RuntimeNativeMainline.with_workspace(root)

        def registry_runner() -> Any:
            raw_result = runner()
            if not isinstance(raw_result, dict):
                return raw_result
            result = copy.deepcopy(raw_result)
            result.setdefault("runtime_route_registry_admission", True)
            result.setdefault("runtime_route_key", record.route_key)
            route = result.get("route")
            if not isinstance(route, dict):
                route = {}
            route.setdefault("runtime_route_registry_admission", True)
            route.setdefault("runtime_route_key", record.route_key)
            result["route"] = route
            return result

        return runtime_mainline.run_compatibility_entry(
            entrypoint=entrypoint,
            runner=registry_runner,
            request=payload,
            goal=run_goal,
            metadata=admission_metadata,
        )


def default_runtime_route_registry() -> RuntimeRouteRegistry:
    registry = RuntimeRouteRegistry()
    registry.register(
        RuntimeRouteKeys.ENGINEERING_TASK,
        _unsupported_default_runner_factory,
        {
            "entrypoint": "core.agent.agent_loop.AgentLoop.engineering_task_route",
            "admission_surface": "agent_loop_engineering_task",
        },
    )
    registry.register(
        RuntimeRouteKeys.WORK_PACKAGE,
        _unsupported_default_runner_factory,
        {
            "entrypoint": "core.agent.agent_loop.AgentLoop.work_package_route",
            "admission_surface": "agent_loop_work_package",
        },
    )
    registry.register(
        RuntimeRouteKeys.ENGINEERING_GOAL,
        _unsupported_default_runner_factory,
        {
            "entrypoint": "core.agent.agent_loop.AgentLoop.engineering_goal_route",
            "admission_surface": "agent_loop_engineering_goal",
        },
    )
    registry.register(
        RuntimeRouteKeys.PLANNER_RUNTIME,
        _unsupported_default_runner_factory,
        {
            "entrypoint": "core.agent.agent_loop.AgentLoop.planner_runtime_dispatch_route",
            "admission_surface": "agent_loop_planner_runtime_dispatch",
        },
    )
    registry.register(
        RuntimeRouteKeys.PERSISTENT_RUNTIME,
        _unsupported_default_runner_factory,
        {
            "entrypoint": "core.agent.agent_loop.AgentLoop.persistent_runtime_route",
            "admission_surface": "agent_loop_persistent_runtime",
        },
    )
    registry.register(
        RuntimeRouteKeys.PLANNER_OWNED_CODE_CHAIN,
        _unsupported_default_runner_factory,
        {
            "entrypoint": "core.agent.agent_loop.AgentLoop.planner_owned_code_chain_route",
            "admission_surface": "agent_loop_planner_owned_code_chain",
        },
    )
    registry.register(
        RuntimeRouteKeys.CODE_CHAIN_CONTROLLED_SELF_EDIT,
        _unsupported_default_runner_factory,
        {
            "entrypoint": "core.agent.agent_loop.AgentLoop.code_chain_controlled_self_edit_bridge_route",
            "admission_surface": "agent_loop_code_chain_controlled_self_edit",
        },
    )
    registry.register(
        RuntimeRouteKeys.AUTONOMOUS_REPAIR,
        _unsupported_default_runner_factory,
        {
            "entrypoint": "core.agent.agent_loop.AgentLoop.autonomous_repair_route",
            "admission_surface": "agent_loop_autonomous_repair",
        },
    )
    registry.register(
        RuntimeRouteKeys.REPAIR_PREFLIGHT,
        _unsupported_default_runner_factory,
        {
            "entrypoint": "core.agent.agent_loop.AgentLoop.repair_preflight_route",
            "admission_surface": "agent_loop_repair_preflight",
        },
    )
    registry.register(
        RuntimeRouteKeys.CLI_TASK_RUN,
        _unsupported_default_runner_factory,
        {"entrypoint": "cli.task_cli.run", "admission_surface": "cli_task_run"},
    )
    registry.register(
        RuntimeRouteKeys.CLI_TASK_DRAIN,
        _unsupported_default_runner_factory,
        {"entrypoint": "cli.task_cli.drain", "admission_surface": "cli_task_drain"},
    )
    registry.register(
        RuntimeRouteKeys.CLI_WORK_PACKAGE_SUBMIT,
        _unsupported_default_runner_factory,
        {"entrypoint": "cli.work_package_cli.submit", "admission_surface": "cli_work_package_submit"},
    )
    registry.register(
        RuntimeRouteKeys.CLI_WORK_PACKAGE_RUN,
        _unsupported_default_runner_factory,
        {"entrypoint": "cli.work_package_cli.run", "admission_surface": "cli_work_package_run"},
    )
    registry.register(
        RuntimeRouteKeys.CLI_WORK_PACKAGE_VALIDATION,
        _unsupported_default_runner_factory,
        {"entrypoint": "cli.work_package_cli.run_validation", "admission_surface": "cli_work_package_validation"},
    )
    registry.register(
        RuntimeRouteKeys.CLI_WORK_PACKAGE_DISPATCH_REQUEST,
        _unsupported_default_runner_factory,
        {
            "entrypoint": "cli.work_package_cli.dispatch_request",
            "admission_surface": "cli_work_package_dispatch_request",
        },
    )
    registry.register(
        RuntimeRouteKeys.CLI_CONTROL_SUBMIT,
        _unsupported_default_runner_factory,
        {"entrypoint": "cli.control_cli.submit", "admission_surface": "cli_control_submit"},
    )
    registry.register(
        RuntimeRouteKeys.CLI_GOAL_RUN,
        _unsupported_default_runner_factory,
        {"entrypoint": "cli.goal_cli.run", "admission_surface": "cli_goal_run"},
    )
    registry.register(
        RuntimeRouteKeys.CLI_GOAL_LOOP,
        _unsupported_default_runner_factory,
        {"entrypoint": "cli.goal_cli.loop", "admission_surface": "cli_goal_loop"},
    )
    registry.register(
        RuntimeRouteKeys.CLI_PORTFOLIO_RUN,
        _unsupported_default_runner_factory,
        {"entrypoint": "cli.portfolio_cli.run_next", "admission_surface": "cli_portfolio_run"},
    )
    registry.register(
        RuntimeRouteKeys.CLI_PORTFOLIO_CYCLE,
        _unsupported_default_runner_factory,
        {"entrypoint": "cli.portfolio_cli.cycle", "admission_surface": "cli_portfolio_cycle"},
    )
    registry.register(
        RuntimeRouteKeys.CLI_PROGRAM_RUN,
        _unsupported_default_runner_factory,
        {"entrypoint": "cli.program_cli.run_next", "admission_surface": "cli_program_run"},
    )
    registry.register(
        RuntimeRouteKeys.CLI_PROGRAM_CYCLE,
        _unsupported_default_runner_factory,
        {"entrypoint": "cli.program_cli.cycle", "admission_surface": "cli_program_cycle"},
    )
    registry.register(
        RuntimeRouteKeys.SCHEDULER_TICK,
        _unsupported_default_runner_factory,
        {"entrypoint": "core.tasks.scheduler.Scheduler.tick", "admission_surface": "scheduler_tick"},
    )
    registry.register(
        RuntimeRouteKeys.SCHEDULER_RUN_STEP,
        _unsupported_default_runner_factory,
        {"entrypoint": "core.tasks.scheduler.Scheduler.run_one_step", "admission_surface": "scheduler_run_step"},
    )
    registry.register(
        RuntimeRouteKeys.SCHEDULER_SUBMIT_TASK,
        _unsupported_default_runner_factory,
        {"entrypoint": "core.tasks.scheduler.Scheduler.submit_task", "admission_surface": "scheduler_submit_task"},
    )
    registry.register(
        RuntimeRouteKeys.TASK_RUNNER_RUN,
        _unsupported_default_runner_factory,
        {"entrypoint": "core.runtime.task_runner.TaskRunner.run_task_tick", "admission_surface": "task_runner_run"},
    )
    registry.register(
        RuntimeRouteKeys.TASK_RUNNER_TICK,
        _unsupported_default_runner_factory,
        {"entrypoint": "core.runtime.task_runner.TaskRunner.run_task_tick", "admission_surface": "task_runner_tick"},
    )
    registry.register(
        RuntimeRouteKeys.TASK_RUNNER_EXECUTE_STEP,
        _unsupported_default_runner_factory,
        {
            "entrypoint": "core.runtime.task_runner.TaskRunner.execute_owned_step",
            "admission_surface": "task_runner_execute_step",
        },
    )
    registry.register(
        RuntimeRouteKeys.TASK_RUNNER_EXECUTE_STEPS,
        _unsupported_default_runner_factory,
        {
            "entrypoint": "core.runtime.task_runner.TaskRunner.execute_owned_steps",
            "admission_surface": "task_runner_execute_steps",
        },
    )
    return registry


def _unsupported_default_runner_factory(
    request: dict[str, Any],
    workspace_root: str | Path,
    goal: str,
) -> CompatibilityRunner:
    route_key = str(request.get("task_type") or request.get("type") or goal or "runtime_route")

    def runner() -> Any:
        raise RuntimeError(f"runtime_route_runner_not_bound:{route_key}")

    return runner


def _normalize_route_key(route_key: str) -> str:
    key = str(route_key or "").strip()
    if not key:
        raise ValueError("runtime_route_key_required")
    return key
