from __future__ import annotations

from core.tasks.execution_runtime_entry import (
    export_execution_runtime_result,
    run_execution_runtime_entry,
)


class ObjectExecutor:
    def execute(self, step):
        return {
            "ok": True,
            "action": step["type"],
            "target_path": step.get("target_path"),
        }


class CustomMethodExecutor:
    def run_step(self, step):
        return {
            "ok": True,
            "action": "custom_run",
            "step_type": step["type"],
        }


class BrokenExecutor:
    def execute(self, step):
        raise RuntimeError("boom")


def test_runtime_entry_invokes_callable_executor():
    def executor(step):
        return {
            "ok": True,
            "action": "called",
            "step_type": step["type"],
        }

    result = run_execution_runtime_entry(
        executor,
        {
            "type": "write_file",
            "path": "workspace/shared/out.txt",
            "content": "hello",
        },
    )

    assert result.ok is True
    assert result.invoked is True
    assert result.invocation_error is None
    assert result.step["type"] == "write_file"
    assert result.step["execution_runtime_entry_invoked"] is True
    assert result.step["execution_runtime_entry_ok"] is True
    assert result.result["action"] == "called"
    assert result.result["step_type"] == "write_file"


def test_runtime_entry_invokes_object_executor():
    result = run_execution_runtime_entry(
        ObjectExecutor(),
        {
            "type": "verify",
            "target_path": "workspace/shared/out.txt",
        },
    )

    assert result.ok is True
    assert result.invoked is True
    assert result.result["action"] == "verify"
    assert result.result["target_path"] == "workspace/shared/out.txt"


def test_runtime_entry_invokes_custom_method_name():
    result = run_execution_runtime_entry(
        CustomMethodExecutor(),
        {
            "action": "run_command",
            "cmd": "python --version",
        },
        method_name="run_step",
    )

    assert result.ok is True
    assert result.invoked is True
    assert result.result["action"] == "custom_run"
    assert result.result["step_type"] == "command"


def test_runtime_entry_rejects_invalid_step_before_invocation():
    result = run_execution_runtime_entry(
        ObjectExecutor(),
        {
            "type": "write_file",
            "content": "missing path",
        },
    )

    assert result.ok is False
    assert result.invoked is False
    assert result.result["action"] == "execution_step_rejected"
    assert "write_file:missing_path" in result.errors
    assert result.step["execution_runtime_entry_invoked"] is False
    assert result.step["execution_runtime_entry_ok"] is False


def test_runtime_entry_handles_executor_exception():
    result = run_execution_runtime_entry(
        BrokenExecutor(),
        {
            "type": "read_file",
            "path": "workspace/shared/input.txt",
        },
    )

    assert result.ok is False
    assert result.invoked is False
    assert result.result["action"] == "execution_invocation_failed"
    assert result.invocation_error is not None
    assert result.invocation_error.startswith("execution_invocation_failed:RuntimeError:boom")


def test_runtime_entry_handles_missing_executor_method():
    result = run_execution_runtime_entry(
        object(),
        {
            "type": "read_file",
            "path": "workspace/shared/input.txt",
        },
    )

    assert result.ok is False
    assert result.invoked is False
    assert result.result["action"] == "execution_invocation_failed"
    assert result.invocation_error is not None
    assert "execution_invocation_failed:AttributeError" in result.invocation_error


def test_export_execution_runtime_result_returns_result_only():
    result = export_execution_runtime_result(
        ObjectExecutor(),
        {
            "type": "append",
            "file_path": "workspace/shared/log.txt",
            "body": "line",
        },
    )

    assert result["ok"] is True
    assert result["action"] == "append_file"
    assert result["target_path"] == "workspace/shared/log.txt"


def test_runtime_entry_normalizes_non_dict_executor_result():
    result = run_execution_runtime_entry(
        lambda step: "done",
        {
            "type": "read",
            "path": "workspace/shared/input.txt",
        },
    )

    assert result.ok is True
    assert result.result["ok"] is True
    assert result.result["action"] == "executor_result"
    assert result.result["result"] == "done"


def test_runtime_entry_normalizes_none_executor_result_as_ok_noop():
    result = run_execution_runtime_entry(
        lambda step: None,
        {
            "type": "noop",
        },
    )

    assert result.ok is True
    assert result.result["ok"] is True
    assert result.result["action"] == "noop"
    assert result.result["result"] is None