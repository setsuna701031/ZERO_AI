from __future__ import annotations

import json
from pathlib import Path

import pytest

import core.agent.agent_loop as agent_loop_module
from core.agent.agent_loop import AgentLoop
from core.runtime.runtime_route_keys import RuntimeRouteKeys
from core.runtime.runtime_route_registry import RuntimeRouteRegistry, default_runtime_route_registry


class _GoalRepository:
    def __init__(self, repo_root):
        self.repo_root = repo_root

    def save_goal(self, record):
        return {"goal_id": record.get("goal_id") or "goal-1", **record}


class _PortfolioRepository:
    def __init__(self, repo_root):
        self.repo_root = repo_root

    def load_portfolio(self, portfolio_id):
        return None

    def create_portfolio(self, record):
        return dict(record)

    def add_goal_to_portfolio(self, portfolio_id, goal_id):
        return {"portfolio_id": portfolio_id, "goal_ids": [goal_id]}


class _ProgramRepository:
    def __init__(self, repo_root):
        self.repo_root = repo_root

    def load_program(self, program_id):
        return None

    def create_program(self, record):
        return dict(record)

    def add_portfolio(self, program_id, portfolio_id):
        return {"program_id": program_id, "portfolio_ids": [portfolio_id]}


class _ProgramCycle:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def run_until_idle(self, program_id, max_portfolios=1):
        return {
            "ok": True,
            "program_id": program_id,
            "portfolio_id": "portfolio-1",
            "goal_id": "goal-1",
            "stop_reason": "idle",
        }


def test_engineering_goal_route_goes_through_runtime_route_registry(monkeypatch, tmp_path) -> None:
    _patch_engineering_goal_stack(monkeypatch)
    calls = _patch_registry_run_observer(monkeypatch)
    loop = AgentLoop(repo_root=str(tmp_path), workspace_dir=str(tmp_path / "workspace"))

    result = loop._try_handle_engineering_goal_route(
        json.dumps(
            {
                "task_type": "engineering_goal",
                "engineering_goal_route": True,
                "goal": "ship wave one",
                "repo_root": str(tmp_path),
                "program_id": "program-1",
                "portfolio_id": "portfolio-1",
                "goal_id": "goal-1",
            }
        )
    )

    assert calls == [RuntimeRouteKeys.ENGINEERING_GOAL]
    assert result["program_result"]["runtime_route_registry_admission"] is True
    assert result["program_result"]["runtime_native_mainline_canonical_entry"] is True
    assert result["route"]["engineering_goal_route"] is True


def test_persistent_runtime_route_goes_through_runtime_route_registry(monkeypatch, tmp_path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)
    monkeypatch.setattr(agent_loop_module, "_zero_v823_run_persistent_runtime_orchestrator", _persistent_runner)
    monkeypatch.setattr(agent_loop_module, "_zero_v823_should_route_persistent_runtime", lambda task, context: True)
    monkeypatch.setattr(agent_loop_module, "_zero_v823_agent_persistent_runtime_candidate", lambda text: True)
    loop = AgentLoop(repo_root=str(tmp_path), workspace_dir=str(tmp_path / "workspace"))

    result = agent_loop_module._zero_v823_agent_try_persistent_runtime_route(loop, "persistent runtime smoke")

    assert calls == [RuntimeRouteKeys.PERSISTENT_RUNTIME]
    assert result["persistent_runtime_orchestrator_payload"]["runtime_route_registry_admission"] is True
    assert result["persistent_runtime_orchestrator_payload"]["runtime_native_mainline_canonical_entry"] is True
    assert result["agent_loop_persistent_runtime_route"] is True


def test_planner_runtime_dispatch_route_goes_through_runtime_route_registry(monkeypatch, tmp_path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)
    monkeypatch.setattr(agent_loop_module, "_zero_v824_dispatch_planner_result_to_persistent_runtime", _planner_dispatch)
    monkeypatch.setattr(agent_loop_module, "_zero_v824_should_dispatch_planner_result_to_persistent_runtime", lambda **kwargs: True)
    monkeypatch.setattr(agent_loop_module, "_zero_v824_agent_planner_dispatch_candidate", lambda text: True)
    monkeypatch.setattr(agent_loop_module, "_zero_v824_call_planner_like", lambda self, context, user_input, route: {"goal": "plan runtime", "steps": []})
    loop = AgentLoop(repo_root=str(tmp_path), workspace_dir=str(tmp_path / "workspace"))

    result = agent_loop_module._zero_v824_agent_try_planner_runtime_dispatch_route(loop, "planner runtime dispatch")

    assert calls == [RuntimeRouteKeys.PLANNER_RUNTIME]
    assert result["planner_runtime_dispatch_payload"]["runtime_route_registry_admission"] is True
    assert result["planner_runtime_dispatch_payload"]["runtime_native_mainline_canonical_entry"] is True
    assert result["agent_loop_planner_runtime_dispatch_route"] is True


def test_current_planner_runtime_entry_goes_through_runtime_route_registry(monkeypatch, tmp_path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)
    monkeypatch.setattr(agent_loop_module, "_zero_v824_dispatch_planner_result_to_persistent_runtime", _planner_dispatch)
    monkeypatch.setattr(agent_loop_module, "_zero_v824_should_dispatch_planner_result_to_persistent_runtime", lambda **kwargs: True)
    monkeypatch.setattr(agent_loop_module, "_zero_v824_agent_planner_dispatch_candidate", lambda text: True)
    monkeypatch.setattr(agent_loop_module, "_zero_v824_call_planner_like", lambda self, context, user_input, route: {"goal": "plan runtime", "steps": []})
    loop = AgentLoop(repo_root=str(tmp_path), workspace_dir=str(tmp_path / "workspace"))

    result = agent_loop_module._zero_v825_agent_try_planner_runtime_dispatch_route(loop, "planner runtime dispatch")

    assert calls == [RuntimeRouteKeys.PLANNER_RUNTIME]
    assert result["planner_runtime_dispatch_payload"]["runtime_route_registry_admission"] is True
    assert result["agent_loop_planner_runtime_dispatch_route"] is True


def test_wave1_registry_dict_result_adds_metadata(tmp_path) -> None:
    registry = RuntimeRouteRegistry()
    registry.register(
        RuntimeRouteKeys.ENGINEERING_GOAL,
        lambda request, workspace_root, goal: lambda: {"ok": True, "goal": goal},
        {"entrypoint": "tests.wave1.engineering_goal"},
    )

    result = registry.run(RuntimeRouteKeys.ENGINEERING_GOAL, {}, tmp_path, "wave goal")

    assert result["ok"] is True
    assert result["goal"] == "wave goal"
    assert result["runtime_route_registry_admission"] is True
    assert result["runtime_native_mainline_canonical_entry"] is True


def test_wave1_registry_exception_reraises(tmp_path) -> None:
    registry = RuntimeRouteRegistry()

    def failing_runner():
        raise RuntimeError("wave1 boom")

    registry.register(
        RuntimeRouteKeys.PERSISTENT_RUNTIME,
        lambda request, workspace_root, goal: failing_runner,
        {"entrypoint": "tests.wave1.persistent_runtime"},
    )

    with pytest.raises(RuntimeError, match="wave1 boom"):
        registry.run(RuntimeRouteKeys.PERSISTENT_RUNTIME, {}, tmp_path, "wave failure")


def test_wave1_delegate_guard_does_not_recurse(monkeypatch, tmp_path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)
    loop = AgentLoop(repo_root=str(tmp_path), workspace_dir=str(tmp_path / "workspace"))
    active = []

    result = loop._run_via_runtime_route_registry(
        route_key=RuntimeRouteKeys.PLANNER_RUNTIME,
        entrypoint="tests.wave1.delegate_guard",
        runner=lambda: active.append(loop._runtime_native_mainline_active()) or {"ok": True},
        request={"goal": "delegate guard"},
        goal="delegate guard",
        workspace_root=tmp_path / "workspace",
    )

    assert calls == [RuntimeRouteKeys.PLANNER_RUNTIME]
    assert result["ok"] is True
    assert active == [True]
    assert loop._runtime_native_mainline_active() is False


def test_default_registry_has_wave1_route_records() -> None:
    registry = default_runtime_route_registry()

    assert registry.has(RuntimeRouteKeys.ENGINEERING_GOAL) is True
    assert registry.has(RuntimeRouteKeys.PLANNER_RUNTIME) is True
    assert registry.has(RuntimeRouteKeys.PERSISTENT_RUNTIME) is True


def _patch_engineering_goal_stack(monkeypatch) -> None:
    monkeypatch.setattr("core.tasks.engineering_goal_repository.EngineeringGoalRepository", _GoalRepository)
    monkeypatch.setattr("core.tasks.engineering_portfolio_repository.EngineeringPortfolioRepository", _PortfolioRepository)
    monkeypatch.setattr("core.tasks.engineering_program_repository.EngineeringProgramRepository", _ProgramRepository)
    monkeypatch.setattr("core.tasks.engineering_program_cycle.EngineeringProgramCycle", _ProgramCycle)


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


def _planner_dispatch(**kwargs):
    return {
        "ok": True,
        "planner_runtime_dispatch": {
            "ok": True,
            "status": "dispatched",
            "orchestrator": {
                "ok": True,
                "status": "finished",
                "session_id": "session-1",
                "cycle_count": 1,
                "closure_count": 1,
            },
        },
    }
