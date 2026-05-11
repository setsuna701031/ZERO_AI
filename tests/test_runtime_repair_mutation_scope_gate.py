from __future__ import annotations

from core.tasks.runtime_repair_mutation_scope_gate import (
    build_runtime_repair_mutation_scope_gate,
)


def test_scope_gate_blocks_when_authorization_is_not_granted():
    result = build_runtime_repair_mutation_scope_gate(
        {
            "task_id": "task_001",
            "proposal_id": "proposal_001",
            "authorized": False,
        },
        target_paths=["workspace/shared/output.txt"],
        requested_actions=["prepare_code_repair"],
    )

    assert result["scope_allowed"] is False
    assert result["scope_status"] == "blocked"
    assert "mutation_authorization_not_granted" in result["blocked_reasons"]
    assert result["mutation_allowed"] is False
    assert result["execution_allowed"] is False
    assert result["schedule_allowed"] is False


def test_scope_gate_allows_safe_preview_inside_workspace_scope():
    result = build_runtime_repair_mutation_scope_gate(
        {
            "task_id": "task_002",
            "proposal_id": "proposal_002",
            "authorized": True,
        },
        target_paths=[
            "workspace/shared/output.txt",
            "workspace/tasks/task_002/patch_preview.diff",
        ],
        requested_actions=[
            "prepare_code_repair",
            "generate_patch_preview",
        ],
    )

    assert result["scope_allowed"] is True
    assert result["scope_status"] == "allowed"
    assert result["allowed_next_action"] == "build_patch_preview"
    assert result["mutation_allowed"] is False
    assert result["execution_allowed"] is False
    assert result["schedule_allowed"] is False
    assert all(item["allowed"] for item in result["path_decisions"])
    assert all(item["allowed"] for item in result["action_decisions"])


def test_scope_gate_blocks_protected_core_paths():
    result = build_runtime_repair_mutation_scope_gate(
        {"authorized": True},
        target_paths=[
            "core/planning/planner.py",
            "app.py",
        ],
        requested_actions=["prepare_code_repair"],
    )

    assert result["scope_allowed"] is False
    assert any("path_blocked:core/planning/planner.py" in item for item in result["blocked_reasons"])
    assert any("path_blocked:app.py" in item for item in result["blocked_reasons"])


def test_scope_gate_blocks_direct_mutating_actions_even_when_authorized():
    result = build_runtime_repair_mutation_scope_gate(
        {"authorized": True},
        target_paths=["workspace/shared/output.txt"],
        requested_actions=[
            "apply_patch",
            "write_file",
            "run_shell_command",
        ],
    )

    assert result["scope_allowed"] is False
    assert any("action_blocked:apply_patch" in item for item in result["blocked_reasons"])
    assert any("action_blocked:write_file" in item for item in result["blocked_reasons"])
    assert any("action_blocked:run_shell_command" in item for item in result["blocked_reasons"])


def test_scope_gate_extracts_paths_and_actions_from_authorization_payload():
    result = build_runtime_repair_mutation_scope_gate(
        {
            "authorized": True,
            "repair_intent": {
                "target_paths": ["workspace/tasks/task_003/repair_plan.json"],
                "proposed_actions": ["propose_repair_plan"],
            },
        }
    )

    assert result["scope_allowed"] is True
    assert result["target_paths"] == ["workspace/tasks/task_003/repair_plan.json"]
    assert result["requested_actions"] == ["propose_repair_plan"]


def test_scope_gate_blocks_unknown_actions_and_outside_paths():
    result = build_runtime_repair_mutation_scope_gate(
        {"authorized": True},
        target_paths=["random/outside.txt"],
        requested_actions=["unknown_tool_call"],
    )

    assert result["scope_allowed"] is False
    assert any("outside_allowed_paths" in reason for reason in result["blocked_reasons"])
    assert any("unknown_action" in reason for reason in result["blocked_reasons"])
