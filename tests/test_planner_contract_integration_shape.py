from __future__ import annotations

from core.planning.planner_contract import normalize_planner_payload


def test_contract_accepts_document_write_shape():
    result = normalize_planner_payload(
        {
            "action": "write_file",
            "target_path": "workspace/shared/summary.txt",
            "content": "summary content",
            "goal": "write summary",
            "metadata": {
                "planner": "document_flow",
                "source": "test",
            },
        }
    )

    assert result.ok is True
    assert result.payload["action"] == "write_file"
    assert result.payload["target_path"] == "workspace/shared/summary.txt"
    assert result.payload["content"] == "summary content"
    assert result.payload["goal"] == "write summary"
    assert result.payload["metadata"]["planner"] == "document_flow"


def test_contract_accepts_verify_shape():
    result = normalize_planner_payload(
        {
            "action": "verify_file",
            "target_path": "workspace/shared/summary.txt",
            "goal": "verify summary output exists",
            "reason": "post write verification",
        }
    )

    assert result.ok is True
    assert result.payload["action"] == "verify_file"
    assert result.payload["target_path"] == "workspace/shared/summary.txt"
    assert result.payload["goal"] == "verify summary output exists"
    assert result.payload["reason"] == "post write verification"


def test_contract_accepts_repair_shape_without_runtime_leakage():
    result = normalize_planner_payload(
        {
            "action": "repair",
            "goal": "repair failed write step",
            "reason": "missing output file",
            "metadata": {
                "runtime_state": "failed",
                "attempt": 1,
                "unsafe_object": object(),
            },
            "unexpected_runtime_field": {
                "should_not": "escape",
            },
        }
    )

    assert result.ok is True
    assert result.payload["action"] == "repair"
    assert result.payload["goal"] == "repair failed write step"
    assert result.payload["reason"] == "missing output file"
    assert result.payload["metadata"] == {
        "runtime_state": "failed",
        "attempt": 1,
    }
    assert "unexpected_runtime_field" not in result.payload


def test_contract_blocks_write_without_target_path():
    result = normalize_planner_payload(
        {
            "action": "write_file",
            "content": "orphan content",
            "goal": "bad planner output",
        }
    )

    assert result.ok is False
    assert result.payload["is_valid"] is False
    assert "write_file:missing_target_path" in result.payload["contract_errors"]


def test_contract_blocks_command_without_command_text():
    result = normalize_planner_payload(
        {
            "action": "run_command",
            "goal": "run something but command is missing",
        }
    )

    assert result.ok is False
    assert result.payload["is_valid"] is False
    assert "run_command:missing_command" in result.payload["contract_errors"]


def test_contract_sanitizes_unknown_planner_action_to_noop():
    result = normalize_planner_payload(
        {
            "action": "invent_scheduler_state",
            "target_path": "workspace/shared/out.txt",
            "content": "should not become executable action",
        }
    )

    assert result.ok is True
    assert result.payload["action"] == "noop"
    assert result.payload["target_path"] == "workspace/shared/out.txt"
    assert result.payload["content"] == "should not become executable action"
    assert "planner_action_unknown:invent_scheduler_state" in result.payload["contract_warnings"]