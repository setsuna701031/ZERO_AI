from __future__ import annotations

from core.tasks.execution_gateway import (
    build_noop_execution_result,
    call_execution_gateway,
    export_execution_gateway_result,
)


class GatewayExecutor:
    def execute(self, step):
        return {
            "ok": True,
            "action": step["type"],
            "target_path": step.get("target_path"),
        }


class GatewayBrokenExecutor:
    def execute(self, step):
        raise RuntimeError("gateway boom")


def test_gateway_accepts_object_executor():
    result = call_execution_gateway(
        GatewayExecutor(),
        {
            "type": "write_file",
            "path": "workspace/shared/out.txt",
            "content": "hello",
        },
        trace=False,
    )

    assert result.ok is True
    assert result.invoked is True
    assert result.gateway_error is None
    assert result.step["type"] == "write_file"
    assert result.step["target_path"] == "workspace/shared/out.txt"
    assert result.step["execution_gateway_ok"] is True
    assert result.step["execution_gateway_invoked"] is True
    assert result.result["action"] == "write_file"
    assert result.result["target_path"] == "workspace/shared/out.txt"
    assert result.result["execution_gateway_ok"] is True


def test_gateway_accepts_callable_executor():
    def executor(step):
        return {
            "ok": True,
            "action": "called",
            "step_type": step["type"],
        }

    result = call_execution_gateway(
        executor,
        {
            "action": "verify_file",
            "target_path": "workspace/shared/out.txt",
        },
        trace=False,
    )

    assert result.ok is True
    assert result.invoked is True
    assert result.step["type"] == "verify"
    assert result.result["action"] == "called"
    assert result.result["step_type"] == "verify"


def test_gateway_blocks_invalid_step_before_executor_invocation():
    result = call_execution_gateway(
        GatewayExecutor(),
        {
            "type": "write_file",
            "content": "missing path",
        },
        trace=False,
    )

    assert result.ok is False
    assert result.invoked is False
    assert result.result["action"] == "execution_step_rejected"
    assert "write_file:missing_path" in result.errors
    assert result.step["execution_gateway_ok"] is False
    assert result.step["execution_gateway_invoked"] is False


def test_gateway_handles_executor_exception():
    result = call_execution_gateway(
        GatewayBrokenExecutor(),
        {
            "type": "read_file",
            "path": "workspace/shared/input.txt",
        },
        trace=False,
    )

    assert result.ok is False
    assert result.invoked is False
    assert result.result["action"] == "execution_invocation_failed"
    assert result.gateway_error is not None
    assert result.gateway_error.startswith("execution_invocation_failed:RuntimeError:gateway boom")
    assert result.step["execution_gateway_ok"] is False


def test_gateway_exports_result_only():
    result = export_execution_gateway_result(
        GatewayExecutor(),
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
    assert result["execution_gateway_ok"] is True


def test_gateway_can_write_trace(tmp_path):
    # Indirect smoke test: tracing enabled should not break gateway execution.
    result = call_execution_gateway(
        GatewayExecutor(),
        {
            "type": "noop",
        },
        trace=True,
    )

    assert result.ok is True
    assert result.result["execution_gateway_ok"] is True


def test_build_noop_execution_result_is_scheduler_safe():
    result = build_noop_execution_result(
        reason="manual fallback",
        step_type="noop",
    )

    assert result["ok"] is True
    assert result["action"] == "noop"
    assert result["reason"] == "manual fallback"
    assert result["execution_gateway_ok"] is True
    assert result["execution_gateway_invoked"] is False
    assert result["step"]["type"] == "noop"
    assert result["step"]["execution_gateway_ok"] is True