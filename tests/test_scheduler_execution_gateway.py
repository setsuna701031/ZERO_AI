from __future__ import annotations

from core.tasks.scheduler_execution_gateway import (
    export_scheduler_step_execution_result,
    run_scheduler_step_execution_gateway,
)


class SchedulerGatewayExecutor:
    def execute(self, step):
        return {
            "ok": True,
            "action": step["type"],
            "target_path": step.get("target_path"),
        }


class SchedulerBrokenExecutor:
    def execute(self, step):
        raise RuntimeError("scheduler gateway boom")


def test_scheduler_execution_gateway_uses_gateway_for_valid_step():
    result = run_scheduler_step_execution_gateway(
        SchedulerGatewayExecutor(),
        {
            "type": "write_file",
            "path": "workspace/shared/out.txt",
            "content": "hello",
        },
        trace=False,
    )

    assert result.ok is True
    assert result.used_gateway is True
    assert result.used_legacy_fallback is False
    assert result.step["type"] == "write_file"
    assert result.step["scheduler_execution_gateway_layer"] == "scheduler_execution_gateway.v1"
    assert result.result["action"] == "write_file"
    assert result.result["scheduler_execution_gateway_layer"] == "scheduler_execution_gateway.v1"
    assert result.result["scheduler_execution_gateway_used"] is True


def test_scheduler_execution_gateway_uses_legacy_fallback_for_invalid_step():
    result = run_scheduler_step_execution_gateway(
        SchedulerGatewayExecutor(),
        {
            "type": "write_file",
            "content": "missing path",
        },
        legacy_result={
            "ok": True,
            "action": "legacy_result",
            "reason": "fallback",
        },
        allow_legacy_fallback=True,
        trace=False,
    )

    assert result.ok is True
    assert result.used_gateway is False
    assert result.used_legacy_fallback is True
    assert result.result["action"] == "legacy_result"
    assert result.result["reason"] == "fallback"
    assert result.result["scheduler_execution_gateway_layer"] == "scheduler_execution_gateway.v1"
    assert "write_file:missing_path" in result.errors


def test_scheduler_execution_gateway_returns_noop_without_fallback():
    result = run_scheduler_step_execution_gateway(
        SchedulerGatewayExecutor(),
        {
            "type": "write_file",
            "content": "missing path",
        },
        allow_legacy_fallback=False,
        trace=False,
    )

    assert result.ok is False
    assert result.used_gateway is False
    assert result.used_legacy_fallback is False
    assert result.result["action"] == "noop"
    assert result.runtime_error is not None
    assert result.result["scheduler_execution_runtime_ok"] is False


def test_scheduler_execution_gateway_handles_executor_exception_with_fallback():
    result = run_scheduler_step_execution_gateway(
        SchedulerBrokenExecutor(),
        {
            "type": "read_file",
            "path": "workspace/shared/input.txt",
        },
        legacy_result={
            "ok": True,
            "action": "legacy_after_exception",
        },
        allow_legacy_fallback=True,
        trace=False,
    )

    assert result.ok is True
    assert result.used_legacy_fallback is True
    assert result.result["action"] == "legacy_after_exception"
    assert result.errors
    assert result.errors[0].startswith("execution_invocation_failed:RuntimeError:scheduler gateway boom")


def test_export_scheduler_step_execution_result_returns_result_only():
    result = export_scheduler_step_execution_result(
        SchedulerGatewayExecutor(),
        {
            "type": "append",
            "file_path": "workspace/shared/log.txt",
            "body": "line",
        },
        trace=False,
    )

    assert result["ok"] is True
    assert result["action"] == "append_file"
    assert result["target_path"] == "workspace/shared/log.txt"
    assert result["scheduler_execution_gateway_layer"] == "scheduler_execution_gateway.v1"