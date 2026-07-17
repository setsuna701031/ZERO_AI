from __future__ import annotations

import pytest

from core.agent.agent_loop import AgentLoop
from core.runtime.runtime_native_mainline import MAINLINE_STATUS_FAILED, RuntimeNativeMainline


def test_compatibility_entry_dict_return_keeps_dict_and_adds_metadata(tmp_path):
    mainline = RuntimeNativeMainline.with_workspace(tmp_path)

    result = mainline.run_compatibility_entry(
        entrypoint="tests.dict_entry",
        runner=lambda: {"ok": True, "value": 42},
        goal="dict goal",
    )

    assert isinstance(result, dict)
    assert result["ok"] is True
    assert result["value"] == 42
    assert result["runtime_native_mainline_canonical_entry"] is True
    assert result["runtime_native_mainline_compatibility_wrapper"] is True


def test_compatibility_entry_truthy_non_dict_returns_raw_value(tmp_path):
    mainline = RuntimeNativeMainline.with_workspace(tmp_path)

    result = mainline.run_compatibility_entry(
        entrypoint="tests.truthy_entry",
        runner=lambda: "ok-string",
        goal="truthy goal",
    )

    assert result == "ok-string"
    assert not isinstance(result, dict)
    assert mainline.latest_result().final_result["result"] == "ok-string"


def test_compatibility_entry_falsy_non_dict_returns_raw_value(tmp_path):
    mainline = RuntimeNativeMainline.with_workspace(tmp_path)

    result = mainline.run_compatibility_entry(
        entrypoint="tests.falsy_entry",
        runner=lambda: None,
        goal="falsy goal",
    )

    assert result is None
    assert mainline.latest_result().final_result["result"] is None


def test_compatibility_entry_exception_records_failure_and_reraises(tmp_path):
    mainline = RuntimeNativeMainline.with_workspace(tmp_path)

    def failing_runner():
        raise RuntimeError("compatibility boom")

    with pytest.raises(RuntimeError, match="compatibility boom"):
        mainline.run_compatibility_entry(
            entrypoint="tests.exception_entry",
            runner=failing_runner,
            goal="exception goal",
        )

    latest = mainline.latest_result()
    assert latest is not None
    assert latest.status == MAINLINE_STATUS_FAILED
    assert latest.final_result["ok"] is False
    assert latest.final_result["error"]["type"] == "RuntimeError"
    assert latest.final_result["error"]["message"] == "compatibility boom"
    assert any(
        event.event_type == "runtime_native_mainline_compatibility_entry_failed"
        and event.run_id == latest.run_id
        for event in mainline.list_events()
    )


def test_agent_loop_runtime_native_delegate_flag_enters_wrapper_once(monkeypatch, tmp_path):
    loop = AgentLoop(workspace_dir=str(tmp_path), repo_root=str(tmp_path))
    calls = []
    active_during_runner = []

    def fake_run_via_runtime_native_mainline(**kwargs):
        calls.append(kwargs["entrypoint"])
        return kwargs["runner"]()

    monkeypatch.setattr(
        "core.runtime.runtime_native_entry_adapter.run_via_runtime_native_mainline",
        fake_run_via_runtime_native_mainline,
    )

    result = loop._run_via_runtime_native_mainline(
        entrypoint="tests.agent_loop_delegate",
        runner=lambda: active_during_runner.append(loop._runtime_native_mainline_active()) or {"ok": True},
        request={"goal": "agent loop delegate"},
        goal="agent loop delegate",
    )

    assert result == {"ok": True}
    assert calls == ["tests.agent_loop_delegate"]
    assert active_during_runner == [True]
    assert loop._runtime_native_mainline_active() is False
