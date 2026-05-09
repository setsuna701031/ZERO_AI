from __future__ import annotations

from core.tasks.planner_gateway_runtime import (
    export_scheduler_runtime_planner_payload,
    run_scheduler_planner_gateway,
)


class RuntimePlanner:
    def plan(self, request):
        return {
            "action": "write_file",
            "target_path": request["target_path"],
            "content": request["content"],
            "goal": request["goal"],
        }


class RuntimeBrokenPlanner:
    def plan(self, request):
        raise RuntimeError("runtime boom")


def test_runtime_gateway_uses_gateway_when_valid():
    result = run_scheduler_planner_gateway(
        RuntimePlanner(),
        {
            "target_path": "workspace/shared/out.txt",
            "content": "hello",
            "goal": "write output",
        },
    )

    assert result.ok is True
    assert result.used_gateway is True
    assert result.used_legacy_fallback is False
    assert result.payload["action"] == "write_file"
    assert result.payload["target_path"] == "workspace/shared/out.txt"
    assert result.payload["scheduler_planner_gateway_used"] is True
    assert result.payload["scheduler_planner_legacy_fallback_used"] is False
    assert result.payload["scheduler_planner_runtime_ok"] is True


def test_runtime_gateway_uses_legacy_fallback_when_gateway_invalid():
    def planner(request):
        return {
            "action": "write_file",
            "content": "missing path",
        }

    legacy_payload = {
        "action": "noop",
        "reason": "legacy fallback",
        "goal": "keep scheduler compatible",
    }

    result = run_scheduler_planner_gateway(
        planner,
        {},
        legacy_payload=legacy_payload,
        allow_legacy_fallback=True,
    )

    assert result.ok is True
    assert result.used_gateway is False
    assert result.used_legacy_fallback is True
    assert result.payload["action"] == "noop"
    assert result.payload["reason"] == "legacy fallback"
    assert result.payload["scheduler_planner_gateway_used"] is False
    assert result.payload["scheduler_planner_legacy_fallback_used"] is True
    assert result.payload["scheduler_planner_runtime_ok"] is True
    assert "write_file:missing_target_path" in result.errors


def test_runtime_gateway_returns_noop_when_invalid_and_no_fallback():
    def planner(request):
        return {
            "action": "write_file",
            "content": "missing path",
        }

    result = run_scheduler_planner_gateway(
        planner,
        {"goal": "bad planner request"},
        allow_legacy_fallback=False,
    )

    assert result.ok is False
    assert result.used_gateway is False
    assert result.used_legacy_fallback is False
    assert result.payload["action"] == "noop"
    assert result.payload["goal"] == "bad planner request"
    assert result.payload["scheduler_planner_runtime_ok"] is False
    assert result.payload["scheduler_planner_runtime_error"] is not None


def test_runtime_gateway_handles_planner_exception_with_legacy_fallback():
    legacy_payload = {
        "action": "noop",
        "reason": "legacy after exception",
    }

    result = run_scheduler_planner_gateway(
        RuntimeBrokenPlanner(),
        {},
        legacy_payload=legacy_payload,
        allow_legacy_fallback=True,
    )

    assert result.ok is True
    assert result.used_legacy_fallback is True
    assert result.payload["action"] == "noop"
    assert result.payload["reason"] == "legacy after exception"
    assert result.payload["scheduler_planner_legacy_fallback_used"] is True
    assert result.errors
    assert result.errors[0].startswith("planner_invocation_failed:RuntimeError:runtime boom")


def test_runtime_gateway_handles_planner_exception_without_fallback():
    result = run_scheduler_planner_gateway(
        RuntimeBrokenPlanner(),
        {"goal": "recover safely"},
        allow_legacy_fallback=False,
    )

    assert result.ok is False
    assert result.payload["action"] == "noop"
    assert result.payload["goal"] == "recover safely"
    assert result.payload["scheduler_planner_runtime_ok"] is False
    assert result.runtime_error is not None
    assert result.runtime_error.startswith("planner_invocation_failed:RuntimeError:runtime boom")


def test_export_scheduler_runtime_planner_payload_returns_payload_only():
    payload = export_scheduler_runtime_planner_payload(
        RuntimePlanner(),
        {
            "target_path": "workspace/shared/out.txt",
            "content": "hello",
            "goal": "write output",
        },
    )

    assert payload["action"] == "write_file"
    assert payload["scheduler_planner_gateway_used"] is True
    assert payload["scheduler_planner_runtime_ok"] is True


def test_runtime_gateway_adds_scheduler_safe_defaults_to_legacy_payload():
    def planner(request):
        return {
            "action": "run_command",
        }

    result = run_scheduler_planner_gateway(
        planner,
        {},
        legacy_payload={"reason": "minimal legacy"},
        allow_legacy_fallback=True,
    )

    assert result.ok is True
    assert result.payload["action"] == "noop"
    assert result.payload["target_path"] is None
    assert result.payload["content"] == ""
    assert result.payload["command"] == ""
    assert result.payload["metadata"] == {}
    assert result.payload["reason"] == "minimal legacy"