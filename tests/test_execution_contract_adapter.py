from __future__ import annotations

from core.tasks.execution_contract_adapter import (
    adapt_execution_step,
    export_runtime_execution_step,
)


def test_adapter_accepts_direct_step():
    result = adapt_execution_step(
        {
            "type": "write_file",
            "path": "workspace/shared/out.txt",
            "content": "hello",
        }
    )

    assert result.ok is True
    assert result.step["type"] == "write_file"
    assert result.step["target_path"] == "workspace/shared/out.txt"
    assert result.step["content"] == "hello"
    assert result.step["execution_adapter_ok"] is True
    assert result.errors == []


def test_adapter_accepts_nested_step_key():
    result = adapt_execution_step(
        {
            "step": {
                "action": "verify_file",
                "target_path": "workspace/shared/out.txt",
                "reason": "check output",
            },
            "noise": {"should": "not leak"},
        }
    )

    assert result.ok is True
    assert result.step["type"] == "verify"
    assert result.step["target_path"] == "workspace/shared/out.txt"
    assert result.step["reason"] == "check output"
    assert "noise" not in result.step


def test_adapter_accepts_nested_payload_key():
    result = adapt_execution_step(
        {
            "payload": {
                "action": "run_command",
                "cmd": "python --version",
            }
        }
    )

    assert result.ok is True
    assert result.step["type"] == "command"
    assert result.step["command"] == "python --version"


def test_adapter_accepts_nested_result_step_key():
    result = adapt_execution_step(
        {
            "result": {
                "step": {
                    "type": "append",
                    "file_path": "workspace/shared/log.txt",
                    "body": "line",
                }
            }
        }
    )

    assert result.ok is True
    assert result.step["type"] == "append_file"
    assert result.step["target_path"] == "workspace/shared/log.txt"
    assert result.step["content"] == "line"


def test_adapter_blocks_invalid_step():
    result = adapt_execution_step(
        {
            "type": "write_file",
            "content": "missing path",
        }
    )

    assert result.ok is False
    assert "write_file:missing_path" in result.errors
    assert result.step["execution_adapter_ok"] is False
    assert "write_file:missing_path" in result.step["execution_adapter_errors"]


def test_adapter_sanitizes_non_mapping_to_noop_failure():
    result = adapt_execution_step(["bad"])

    assert result.ok is False
    assert result.step["type"] == "noop"
    assert "execution_step_not_mapping:list" in result.errors


def test_export_runtime_execution_step_returns_step_only():
    step = export_runtime_execution_step(
        {
            "payload": {
                "type": "read",
                "path": "workspace/shared/input.txt",
                "metadata": {
                    "source": "unit_test",
                    "unsafe": object(),
                },
            }
        }
    )

    assert step["type"] == "read_file"
    assert step["path"] == "workspace/shared/input.txt"
    assert step["metadata"] == {"source": "unit_test"}
    assert step["execution_adapter_ok"] is True