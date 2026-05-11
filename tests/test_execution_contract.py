from __future__ import annotations

from core.tasks.execution_contract import (
    EXECUTION_CONTRACT_VERSION,
    normalize_execution_step,
    sanitize_execution_step,
    validate_execution_step,
)


def test_missing_step_becomes_noop_with_warning():
    result = normalize_execution_step(None)

    assert result.ok is True
    assert result.step["type"] == "noop"
    assert result.step["contract_version"] == EXECUTION_CONTRACT_VERSION
    assert "execution_step_missing" in result.warnings


def test_rejects_non_mapping_step():
    result = normalize_execution_step(["bad"])

    assert result.ok is False
    assert result.step["type"] == "noop"
    assert result.errors == ["execution_step_not_mapping:list"]


def test_normalizes_write_file_step():
    result = normalize_execution_step(
        {
            "type": "write_file",
            "path": "workspace\\shared\\out.txt",
            "content": "hello",
            "metadata": {"source": "unit_test", "unsafe": object()},
        }
    )

    assert result.ok is True
    assert result.step["type"] == "write_file"
    assert result.step["path"] == "workspace/shared/out.txt"
    assert result.step["target_path"] == "workspace/shared/out.txt"
    assert result.step["content"] == "hello"
    assert result.step["metadata"] == {"source": "unit_test"}


def test_write_file_requires_path():
    result = normalize_execution_step(
        {
            "type": "write_file",
            "content": "missing path",
        }
    )

    assert result.ok is False
    assert "write_file:missing_path" in result.errors
    assert result.step["is_valid"] is False


def test_verify_file_alias_becomes_verify():
    result = normalize_execution_step(
        {
            "action": "verify_file",
            "target_path": "workspace/shared/out.txt",
            "reason": "post-write check",
        }
    )

    assert result.ok is True
    assert result.step["type"] == "verify"
    assert result.step["target_path"] == "workspace/shared/out.txt"
    assert result.step["reason"] == "post-write check"


def test_run_command_alias_becomes_command():
    result = normalize_execution_step(
        {
            "action": "run_command",
            "cmd": "python --version",
        }
    )

    assert result.ok is True
    assert result.step["type"] == "command"
    assert result.step["command"] == "python --version"


def test_command_requires_command_text():
    result = normalize_execution_step({"type": "command"})

    assert result.ok is False
    assert "command:missing_command" in result.errors


def test_unknown_step_type_sanitizes_to_noop():
    result = normalize_execution_step(
        {
            "type": "invent_executor_mode",
            "content": "should not execute",
        }
    )

    assert result.ok is True
    assert result.step["type"] == "noop"
    assert "execution_step_type_unknown:invent_executor_mode" in result.warnings


def test_sanitize_returns_step_only():
    step = sanitize_execution_step(
        {
            "type": "append",
            "file_path": "workspace/shared/log.txt",
            "body": "line",
        }
    )

    assert step["type"] == "append_file"
    assert step["target_path"] == "workspace/shared/log.txt"
    assert step["content"] == "line"


def test_validate_is_same_entrypoint():
    result = validate_execution_step(
        {
            "kind": "read",
            "path": "workspace/shared/input.txt",
        }
    )

    assert result.ok is True
    assert result.step["type"] == "read_file"
    assert result.step["path"] == "workspace/shared/input.txt"