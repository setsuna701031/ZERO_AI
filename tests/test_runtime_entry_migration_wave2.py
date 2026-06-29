from __future__ import annotations

from pathlib import Path

import pytest

import core.agent.agent_loop as agent_loop_module
from core.agent.agent_loop import AgentLoop
from core.runtime.runtime_route_keys import RuntimeRouteKeys
from core.runtime.runtime_route_registry import RuntimeRouteRegistry, default_runtime_route_registry


def test_planner_owned_code_chain_goes_through_runtime_route_registry(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)
    monkeypatch.setattr(agent_loop_module, "_zero_v824_agent_planner_dispatch_candidate", lambda text: False)
    monkeypatch.setattr(agent_loop_module, "_zero_v823_agent_persistent_runtime_candidate", lambda text: False)
    monkeypatch.setattr(agent_loop_module, "_zero_v827_run_planner_owned_code_chain_bridge", _planner_owned_bridge)
    loop = AgentLoop(repo_root=str(tmp_path), workspace_dir=str(tmp_path / "workspace"))

    result = agent_loop_module._zero_v827_agent_try_planner_owned_code_chain(loop, "planner-owned code chain")

    assert calls == [RuntimeRouteKeys.PLANNER_OWNED_CODE_CHAIN]
    assert result["runtime_route_registry_admission"] is True
    assert result["runtime_native_mainline_canonical_entry"] is True
    assert result["mode"] == "code_chain_controlled_self_edit_bridge"


def test_controlled_self_edit_bridge_goes_through_runtime_route_registry(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)
    monkeypatch.setattr(agent_loop_module, "_zero_v827_run_planner_owned_code_chain_bridge", None)
    monkeypatch.setattr(agent_loop_module, "_zero_v826_code_fix_bridge_candidate", lambda text: True)
    monkeypatch.setattr(agent_loop_module, "_zero_v824_call_planner_like", lambda *args, **kwargs: {"steps": []})
    monkeypatch.setattr(agent_loop_module, "_zero_v826_agent_try_code_chain_controlled_self_edit_bridge", _controlled_bridge)
    loop = AgentLoop(repo_root=str(tmp_path), workspace_dir=str(tmp_path / "workspace"))

    result = loop._try_agent_loop_pre_routes("fix code through controlled bridge")

    assert calls == [RuntimeRouteKeys.CODE_CHAIN_CONTROLLED_SELF_EDIT]
    assert result["runtime_route_registry_admission"] is True
    assert result["agent_loop_runtime_route"] == "code_chain_controlled_self_edit_bridge"


def test_repair_preflight_response_goes_through_runtime_route_registry(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)
    monkeypatch.setattr(agent_loop_module, "_zero_v827_run_planner_owned_code_chain_bridge", None)
    monkeypatch.setattr(agent_loop_module, "_zero_v826_code_fix_bridge_candidate", lambda text: False)
    monkeypatch.setattr(agent_loop_module, "_zero_v710_looks_like_repair_intent", lambda text: True)
    monkeypatch.setattr(
        agent_loop_module,
        "_zero_v710_repair_scope_decision",
        lambda text: {"ok": False, "error": "repair_scope_blocked", "reason": "blocked", "target_path": "core/a.py"},
    )
    loop = AgentLoop(repo_root=str(tmp_path), workspace_dir=str(tmp_path / "workspace"))

    result = loop._try_agent_loop_pre_routes("repair core/a.py")

    assert calls == [RuntimeRouteKeys.REPAIR_PREFLIGHT]
    assert result["runtime_route_registry_admission"] is True
    assert result["agent_loop_runtime_route"] == "code_chain_repair_preflight"
    assert result["route"]["mode"] == "code_chain_repair_preflight"


def test_autonomous_repair_execution_goes_through_runtime_route_registry(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_registry_run_observer(monkeypatch)
    monkeypatch.setattr(agent_loop_module, "_zero_v827_run_planner_owned_code_chain_bridge", None)
    monkeypatch.setattr(agent_loop_module, "_zero_v826_code_fix_bridge_candidate", lambda text: False)
    monkeypatch.setattr(agent_loop_module, "_zero_v710_looks_like_repair_intent", lambda text: False)
    monkeypatch.setattr(agent_loop_module, "_zero_v7_0_1_looks_like_autonomous_repair", lambda text: True)
    monkeypatch.setattr(agent_loop_module, "_zero_v7_0_1_extract_workspace_py_path", lambda text: "workspace/shared/a.py")
    monkeypatch.setattr(AgentLoop, "_run_task_mode", lambda self, **kwargs: {"ok": True, "mode": "task", "route": kwargs["route"]})
    loop = AgentLoop(repo_root=str(tmp_path), workspace_dir=str(tmp_path / "workspace"))

    result = loop._try_agent_loop_pre_routes("autonomous repair workspace/shared/a.py")

    assert calls == [RuntimeRouteKeys.AUTONOMOUS_REPAIR]
    assert result["runtime_route_registry_admission"] is True
    assert result["agent_loop_runtime_route"] == "planner_autonomous_repair"
    assert result["route"]["planner_autonomous_repair"] is True


def test_default_registry_has_wave2_route_records() -> None:
    registry = default_runtime_route_registry()

    assert registry.has(RuntimeRouteKeys.PLANNER_OWNED_CODE_CHAIN) is True
    assert registry.has(RuntimeRouteKeys.CODE_CHAIN_CONTROLLED_SELF_EDIT) is True
    assert registry.has(RuntimeRouteKeys.AUTONOMOUS_REPAIR) is True
    assert registry.has(RuntimeRouteKeys.REPAIR_PREFLIGHT) is True


def test_wave2_registry_non_dict_result_returns_raw_value(tmp_path: Path) -> None:
    registry = RuntimeRouteRegistry()
    registry.register(
        RuntimeRouteKeys.PLANNER_OWNED_CODE_CHAIN,
        lambda request, workspace_root, goal: lambda: "raw-wave2-result",
        {"entrypoint": "tests.wave2.raw"},
    )

    result = registry.run(RuntimeRouteKeys.PLANNER_OWNED_CODE_CHAIN, {}, tmp_path, "raw wave2")

    assert result == "raw-wave2-result"
    assert not isinstance(result, dict)


def test_wave2_registry_exception_reraises(tmp_path: Path) -> None:
    registry = RuntimeRouteRegistry()

    def failing_runner():
        raise RuntimeError("wave2 boom")

    registry.register(
        RuntimeRouteKeys.AUTONOMOUS_REPAIR,
        lambda request, workspace_root, goal: failing_runner,
        {"entrypoint": "tests.wave2.failure"},
    )

    with pytest.raises(RuntimeError, match="wave2 boom"):
        registry.run(RuntimeRouteKeys.AUTONOMOUS_REPAIR, {}, tmp_path, "wave2 failure")


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


def _planner_owned_bridge(**kwargs):
    return {
        "ok": False,
        "mode": "code_chain_controlled_self_edit_bridge",
        "planner_owned_intent_routing": True,
    }


def _controlled_bridge(self, user_input: str):
    return {
        "ok": False,
        "mode": "code_chain_controlled_self_edit_bridge",
        "code_chain_controlled_self_edit_bridge": True,
    }
