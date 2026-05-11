from __future__ import annotations

from core.planning.planner_contract import (
    PLANNER_CONTRACT_VERSION,
    normalize_planner_payload,
    sanitize_planner_payload,
    validate_planner_payload,
)


def test_normalize_missing_payload_becomes_noop_with_warning():
    result = normalize_planner_payload(None)

    assert result.ok is True
    assert result.payload["action"] == "noop"
    assert result.payload["contract_version"] == PLANNER_CONTRACT_VERSION
    assert "planner_payload_missing" in result.warnings


def test_rejects_non_mapping_payload():
    result = normalize_planner_payload(["not", "a", "mapping"])

    assert result.ok is False
    assert result.payload["action"] == "noop"
    assert result.errors == ["planner_payload_not_mapping:list"]


def test_normalizes_action_aliases():
    result = normalize_planner_payload(
        {
            "type": "write",
            "path": "workspace\\shared\\hello.txt",
            "text": "hello",
        }
    )

    assert result.ok is True
    assert result.payload["action"] == "write_file"
    assert result.payload["target_path"] == "workspace/shared/hello.txt"
    assert result.payload["content"] == "hello"


def test_unknown_action_is_sanitized_to_noop():
    result = normalize_planner_payload({"action": "invent_new_runtime_mode"})

    assert result.ok is True
    assert result.payload["action"] == "noop"
    assert "planner_action_unknown:invent_new_runtime_mode" in result.warnings


def test_write_file_requires_target_path():
    result = normalize_planner_payload({"action": "write_file", "content": "abc"})

    assert result.ok is False
    assert "write_file:missing_target_path" in result.errors
    assert result.payload["is_valid"] is False
    assert "write_file:missing_target_path" in result.payload["contract_errors"]


def test_run_command_requires_command():
    result = normalize_planner_payload({"action": "run_command"})

    assert result.ok is False
    assert "run_command:missing_command" in result.errors


def test_sanitize_returns_payload_only():
    payload = sanitize_planner_payload(
        {
            "action": "append",
            "filename": "workspace/shared/log.txt",
            "body": "line",
            "metadata": {"source": "test", "nested": {"ok": True, "bad": object()}},
        }
    )

    assert payload["action"] == "append_file"
    assert payload["target_path"] == "workspace/shared/log.txt"
    assert payload["content"] == "line"
    assert payload["metadata"]["source"] == "test"
    assert payload["metadata"]["nested"] == {"ok": True}


def test_validate_is_same_contract_entrypoint():
    result = validate_planner_payload(
        {
            "kind": "verify",
            "file_path": "workspace/shared/out.txt",
            "goal": "verify output",
        }
    )

    assert result.ok is True
    assert result.payload["action"] == "verify_file"
    assert result.payload["target_path"] == "workspace/shared/out.txt"
    assert result.payload["goal"] == "verify output"