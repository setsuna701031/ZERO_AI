from __future__ import annotations

from core.tasks.execution_gateway_runtime import (
    export_scheduler_execution_result,
    run_scheduler_execution_gateway,
)


class RuntimeExecutor:
    def execute(self, step):
        return {
            "ok": True,
            "action": step["type"],
            "target_path": step.get("target_path"),
        }


class RuntimeBrokenExecutor:
    def execute(self, step):
        raise RuntimeError("runtime boom")


def test_runtime_gateway_uses_gateway_when_valid():
    result = run_scheduler_execution_gateway(
        RuntimeExecutor(),
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
    assert result.result["action"] == "write_file"
    assert result.step["scheduler_execution_gateway_used"] is True
    assert result.result["scheduler_execution_gateway_used"] is True
    assert result.step["scheduler_execution_runtime_ok"] is True
    assert result.result["scheduler_execution_runtime_ok"] is True


def test_runtime_gateway_uses_legacy_fallback_when_gateway_invalid():
    legacy_result = {
        "ok": True,
        "action": "legacy_write",
        "reason": "legacy fallback",
    }

    result = run_scheduler_execution_gateway(
        RuntimeExecutor(),
        {
            "type": "write_file",
            "content": "missing path",
        },
        legacy_result=legacy_result,
        allow_legacy_fallback=True,
        trace=False,
    )

    assert result.ok is True
    assert result.used_gateway is False
    assert result.used_legacy_fallback is True
    assert result.result["action"] == "legacy_write"
    assert result.result["reason"] == "legacy fallback"
    assert result.step["scheduler_execution_gateway_used"] is False
    assert result.result["scheduler_execution_legacy_fallback_used"] is True
    assert "write_file:missing_path" in result.errors


def test_runtime_gateway_returns_noop_when_invalid_and_no_fallback():
    result = run_scheduler_execution_gateway(
        RuntimeExecutor(),
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
    assert result.step["scheduler_execution_runtime_ok"] is False
    assert result.result["scheduler_execution_runtime_ok"] is False
    assert result.runtime_error is not None


def test_runtime_gateway_handles_executor_exception_with_legacy_fallback():
    legacy_result = {
        "ok": True,
        "action": "legacy_after_exception",
        "reason": "legacy after exception",
    }

    result = run_scheduler_execution_gateway(
        RuntimeBrokenExecutor(),
        {
            "type": "read_file",
            "path": "workspace/shared/input.txt",
        },
        legacy_result=legacy_result,
        allow_legacy_fallback=True,
        trace=False,
    )

    assert result.ok is True
    assert result.used_legacy_fallback is True
    assert result.result["action"] == "legacy_after_exception"
    assert result.result["scheduler_execution_legacy_fallback_used"] is True
    assert result.errors
    assert result.errors[0].startswith("execution_invocation_failed:RuntimeError:runtime boom")


def test_runtime_gateway_handles_executor_exception_without_fallback():
    result = run_scheduler_execution_gateway(
        RuntimeBrokenExecutor(),
        {
            "type": "read_file",
            "path": "workspace/shared/input.txt",
        },
        allow_legacy_fallback=False,
        trace=False,
    )

    assert result.ok is False
    assert result.result["action"] == "noop"
    assert result.step["scheduler_execution_runtime_ok"] is False
    assert result.runtime_error is not None
    assert result.runtime_error.startswith("execution_invocation_failed:RuntimeError:runtime boom")


def test_export_scheduler_execution_result_returns_result_only():
    result = export_scheduler_execution_result(
        RuntimeExecutor(),
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
    assert result["scheduler_execution_gateway_used"] is True
    assert result["scheduler_execution_runtime_ok"] is True


def test_runtime_gateway_adds_scheduler_safe_defaults_to_legacy_result():
    legacy_result = {
        "action": "legacy_minimal",
    }

    result = run_scheduler_execution_gateway(
        RuntimeExecutor(),
        {
            "type": "command",
        },
        legacy_result=legacy_result,
        allow_legacy_fallback=True,
        trace=False,
    )

    assert result.ok is True
    assert result.used_legacy_fallback is True
    assert result.result["action"] == "legacy_minimal"
    assert result.result["ok"] is True
    assert result.result["error"] == ""
    assert result.result["scheduler_execution_gateway_used"] is False
    assert result.step["type"] == "command"
    assert result.step["scheduler_execution_legacy_fallback_used"] is True