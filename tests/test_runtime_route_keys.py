from __future__ import annotations

import pytest

from core.runtime.runtime_native_mainline import RuntimeNativeMainline
from core.runtime.runtime_route_keys import RuntimeRouteKeys
from core.runtime.runtime_route_registry import RuntimeRouteRegistry, default_runtime_route_registry


def test_runtime_route_keys_canonical_values() -> None:
    assert RuntimeRouteKeys.ENGINEERING_TASK == "engineering_task"
    assert RuntimeRouteKeys.WORK_PACKAGE == "work_package"
    assert RuntimeRouteKeys.PLANNER_OWNED_CODE_CHAIN == "planner_owned_code_chain"
    assert RuntimeRouteKeys.CODE_CHAIN_CONTROLLED_SELF_EDIT == "code_chain_controlled_self_edit"
    assert RuntimeRouteKeys.AUTONOMOUS_REPAIR == "autonomous_repair"
    assert RuntimeRouteKeys.REPAIR_PREFLIGHT == "repair_preflight"
    assert RuntimeRouteKeys.CLI_TASK_RUN == "cli_task_run"
    assert RuntimeRouteKeys.CLI_TASK_DRAIN == "cli_task_drain"
    assert RuntimeRouteKeys.CLI_WORK_PACKAGE_RUN == "cli_work_package_run"
    assert RuntimeRouteKeys.CLI_CONTROL_SUBMIT == "cli_control_submit"
    assert RuntimeRouteKeys.SCHEDULER_RUN_STEP == "scheduler_run_step"
    assert RuntimeRouteKeys.SCHEDULER_TICK == "scheduler_tick"
    assert RuntimeRouteKeys.TASK_RUNNER_RUN == "task_runner_run"
    assert RuntimeRouteKeys.TASK_RUNNER_TICK == "task_runner_tick"


def test_default_registry_has_canonical_agent_loop_keys() -> None:
    registry = default_runtime_route_registry()

    assert registry.has(RuntimeRouteKeys.ENGINEERING_TASK) is True
    assert registry.has(RuntimeRouteKeys.WORK_PACKAGE) is True
    assert registry.has(RuntimeRouteKeys.PLANNER_OWNED_CODE_CHAIN) is True
    assert registry.has(RuntimeRouteKeys.CODE_CHAIN_CONTROLLED_SELF_EDIT) is True
    assert registry.has(RuntimeRouteKeys.AUTONOMOUS_REPAIR) is True
    assert registry.has(RuntimeRouteKeys.REPAIR_PREFLIGHT) is True
    assert registry.has(RuntimeRouteKeys.CLI_TASK_RUN) is True
    assert registry.has(RuntimeRouteKeys.CLI_TASK_DRAIN) is True
    assert registry.has(RuntimeRouteKeys.CLI_WORK_PACKAGE_RUN) is True
    assert registry.has(RuntimeRouteKeys.CLI_CONTROL_SUBMIT) is True
    assert registry.has(RuntimeRouteKeys.SCHEDULER_RUN_STEP) is True
    assert registry.has(RuntimeRouteKeys.SCHEDULER_TICK) is True
    assert registry.has(RuntimeRouteKeys.TASK_RUNNER_RUN) is True
    assert registry.has(RuntimeRouteKeys.TASK_RUNNER_TICK) is True


def test_registry_run_with_canonical_key_uses_compatibility_entry(tmp_path) -> None:
    registry = RuntimeRouteRegistry()
    registry.register(
        RuntimeRouteKeys.ENGINEERING_TASK,
        lambda request, workspace_root, goal: lambda: {"ok": True, "package_id": request["package_id"]},
        {"entrypoint": "tests.canonical_engineering_task"},
    )
    mainline = RuntimeNativeMainline.with_workspace(tmp_path)

    result = registry.run(
        RuntimeRouteKeys.ENGINEERING_TASK,
        {"package_id": "pkg-1"},
        tmp_path,
        "canonical goal",
        mainline=mainline,
    )

    assert result["ok"] is True
    assert result["package_id"] == "pkg-1"
    assert result["runtime_route_key"] == RuntimeRouteKeys.ENGINEERING_TASK
    assert result["runtime_native_mainline_canonical_entry"] is True
    assert mainline.latest_result().metadata["runtime_route_key"] == RuntimeRouteKeys.ENGINEERING_TASK


def test_registry_non_dict_semantics_unchanged_for_canonical_key(tmp_path) -> None:
    registry = RuntimeRouteRegistry()
    registry.register(
        RuntimeRouteKeys.WORK_PACKAGE,
        lambda request, workspace_root, goal: lambda: "raw-work-package-result",
        {"entrypoint": "tests.canonical_work_package_raw"},
    )

    result = registry.run(RuntimeRouteKeys.WORK_PACKAGE, {}, tmp_path, "raw canonical goal")

    assert result == "raw-work-package-result"
    assert not isinstance(result, dict)


def test_registry_exception_semantics_unchanged_for_canonical_key(tmp_path) -> None:
    registry = RuntimeRouteRegistry()

    def failing_runner():
        raise RuntimeError("canonical route boom")

    registry.register(
        RuntimeRouteKeys.WORK_PACKAGE,
        lambda request, workspace_root, goal: failing_runner,
        {"entrypoint": "tests.canonical_work_package_failure"},
    )

    with pytest.raises(RuntimeError, match="canonical route boom"):
        registry.run(RuntimeRouteKeys.WORK_PACKAGE, {}, tmp_path, "failing canonical goal")
