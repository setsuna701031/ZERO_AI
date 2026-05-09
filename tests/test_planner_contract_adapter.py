from __future__ import annotations

from core.planning.planner_contract_adapter import (
    adapt_planner_result,
    export_runtime_safe_payload,
)


def test_adapter_accepts_direct_planner_payload():
    result = adapt_planner_result(
        {
            "action": "write_file",
            "target_path": "workspace/shared/out.txt",
            "content": "hello",
            "goal": "write output",
        }
    )

    assert result.ok is True
    assert result.payload["action"] == "write_file"
    assert result.payload["target_path"] == "workspace/shared/out.txt"
    assert result.payload["content"] == "hello"
    assert result.payload["adapter_ok"] is True
    assert result.errors == []


def test_adapter_accepts_nested_payload_key():
    result = adapt_planner_result(
        {
            "ok": True,
            "payload": {
                "action": "verify_file",
                "target_path": "workspace/shared/out.txt",
                "goal": "verify output",
            },
            "runtime_noise": {"should": "not leak"},
        }
    )

    assert result.ok is True
    assert result.payload["action"] == "verify_file"
    assert result.payload["target_path"] == "workspace/shared/out.txt"
    assert "runtime_noise" not in result.payload


def test_adapter_accepts_nested_plan_key():
    result = adapt_planner_result(
        {
            "plan": {
                "type": "append",
                "filename": "workspace/shared/log.txt",
                "body": "line",
            }
        }
    )

    assert result.ok is True
    assert result.payload["action"] == "append_file"
    assert result.payload["target_path"] == "workspace/shared/log.txt"
    assert result.payload["content"] == "line"


def test_adapter_accepts_nested_result_key():
    result = adapt_planner_result(
        {
            "result": {
                "kind": "run",
                "cmd": "python --version",
            }
        }
    )

    assert result.ok is True
    assert result.payload["action"] == "run_command"
    assert result.payload["command"] == "python --version"


def test_adapter_blocks_invalid_planner_payload():
    result = adapt_planner_result(
        {
            "action": "write_file",
            "content": "missing path",
        }
    )

    assert result.ok is False
    assert result.payload["adapter_ok"] is False
    assert "write_file:missing_target_path" in result.errors
    assert "write_file:missing_target_path" in result.payload["adapter_errors"]


def test_adapter_sanitizes_non_mapping_to_noop_failure():
    result = adapt_planner_result(["bad", "planner", "result"])

    assert result.ok is False
    assert result.payload["action"] == "noop"
    assert "planner_payload_not_mapping:list" in result.errors


def test_export_runtime_safe_payload_returns_payload_only():
    payload = export_runtime_safe_payload(
        {
            "payload": {
                "action": "repair",
                "goal": "repair failed task",
                "reason": "contract mismatch",
                "metadata": {
                    "attempt": 2,
                    "unsafe": object(),
                },
            }
        }
    )

    assert payload["action"] == "repair"
    assert payload["goal"] == "repair failed task"
    assert payload["reason"] == "contract mismatch"
    assert payload["metadata"] == {"attempt": 2}
    assert payload["adapter_ok"] is True