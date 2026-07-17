from __future__ import annotations

import pytest

from core.agent.agent_loop import AgentLoop
from core.runtime.runtime_native_mainline import RuntimeNativeMainline
from core.runtime.runtime_route_keys import RuntimeRouteKeys
from core.runtime.runtime_route_registry import RuntimeRouteRegistry, default_runtime_route_registry
pytestmark = [pytest.mark.contract, pytest.mark.contract_fast]




def test_registry_register_get_has_route() -> None:
    registry = RuntimeRouteRegistry()

    record = registry.register(
        "sample_route",
        lambda request, workspace_root, goal: lambda: {"ok": True},
        {"entrypoint": "tests.sample_route"},
    )

    assert registry.has("sample_route") is True
    assert registry.get("sample_route") == record
    assert registry.get("sample_route").metadata["entrypoint"] == "tests.sample_route"


def test_default_registry_admits_agent_loop_route_keys() -> None:
    registry = default_runtime_route_registry()

    assert registry.has(RuntimeRouteKeys.ENGINEERING_TASK) is True
    assert registry.has(RuntimeRouteKeys.WORK_PACKAGE) is True


def test_registry_run_uses_runtime_native_mainline_compatibility_entry(tmp_path) -> None:
    registry = RuntimeRouteRegistry()
    registry.register(
        "dict_route",
        lambda request, workspace_root, goal: lambda: {"ok": True, "value": request["value"]},
        {"entrypoint": "tests.registry_dict_route"},
    )
    mainline = RuntimeNativeMainline.with_workspace(tmp_path)

    result = registry.run(
        "dict_route",
        {"value": 42},
        tmp_path,
        "registry goal",
        mainline=mainline,
    )

    assert result["ok"] is True
    assert result["value"] == 42
    assert result["runtime_route_registry_admission"] is True
    assert result["runtime_route_key"] == "dict_route"
    assert result["runtime_native_mainline_canonical_entry"] is True
    assert mainline.latest_result().metadata["runtime_route_key"] == "dict_route"


def test_registry_dict_result_keeps_dict_and_canonical_metadata(tmp_path) -> None:
    registry = RuntimeRouteRegistry()
    registry.register(
        "metadata_route",
        lambda request, workspace_root, goal: lambda: {"ok": True, "nested": {"kept": True}},
        {"entrypoint": "tests.metadata_route"},
    )

    result = registry.run("metadata_route", {}, tmp_path, "metadata goal")

    assert isinstance(result, dict)
    assert result["nested"] == {"kept": True}
    assert result["runtime_route_registry_admission"] is True
    assert result["route"]["runtime_route_registry_admission"] is True
    assert result["runtime_native_mainline_compatibility_wrapper"] is True


def test_registry_non_dict_result_returns_raw_value(tmp_path) -> None:
    registry = RuntimeRouteRegistry()
    registry.register(
        "raw_route",
        lambda request, workspace_root, goal: lambda: "raw-value",
        {"entrypoint": "tests.raw_route"},
    )

    result = registry.run("raw_route", {}, tmp_path, "raw goal")

    assert result == "raw-value"
    assert not isinstance(result, dict)


def test_registry_exception_reraises(tmp_path) -> None:
    registry = RuntimeRouteRegistry()

    def failing_runner():
        raise RuntimeError("registry boom")

    registry.register(
        "failing_route",
        lambda request, workspace_root, goal: failing_runner,
        {"entrypoint": "tests.failing_route"},
    )

    with pytest.raises(RuntimeError, match="registry boom"):
        registry.run("failing_route", {}, tmp_path, "failing goal")


def test_agent_loop_route_registry_helper_does_not_reenter_compatibility(monkeypatch, tmp_path) -> None:
    loop = AgentLoop(workspace_dir=str(tmp_path), repo_root=str(tmp_path))
    calls = []
    active_during_runner = []

    def fake_registry_run(self, route_key, request, workspace_root, goal, mainline=None):
        calls.append(route_key)
        record = self.get(route_key)
        runner = record.runner_factory(request or {}, workspace_root, goal)
        return runner()

    monkeypatch.setattr(
        "core.runtime.runtime_route_registry.RuntimeRouteRegistry.run",
        fake_registry_run,
    )

    result = loop._run_via_runtime_route_registry(
        route_key=RuntimeRouteKeys.ENGINEERING_TASK,
        entrypoint="tests.agent_loop_registry_delegate",
        runner=lambda: active_during_runner.append(loop._runtime_native_mainline_active()) or {"ok": True},
        request={"goal": "agent loop registry delegate"},
        goal="agent loop registry delegate",
        workspace_root=tmp_path,
    )

    assert result == {"ok": True}
    assert calls == [RuntimeRouteKeys.ENGINEERING_TASK]
    assert active_during_runner == [True]
    assert loop._runtime_native_mainline_active() is False
