from __future__ import annotations

from core.tasks.runtime_repair_planner_bridge import (
    build_runtime_repair_planner_bridge,
    build_runtime_repair_planner_bridges,
)


def test_runtime_repair_planner_bridge_blocks_high_risk_confirmation_scope():
    bridge = build_runtime_repair_planner_bridge(
        {
            "task_id": "task_001",
            "status": "failed",
            "repair_mode": "manual_review",
            "repair_scope": "code_execution_review",
            "repair_risk": "high",
            "requires_confirmation": True,
            "allowed_actions": [
                "inspect_runtime_state",
                "inspect_execution_log",
                "inspect_trace",
                "propose_repair_plan",
                "prepare_code_repair",
            ],
            "blocked_actions": [
                "schedule_task",
                "apply_patch",
                "write_file",
                "run_shell_command",
            ],
            "inspection_targets": ["execution_log.json", "trace.json"],
            "suggestion_type": "inspect_python_failure",
            "max_retry": 0,
        }
    )

    assert bridge["ok"] is True
    assert bridge["planner_allowed"] is False
    assert bridge["repair_intent"]["intent_type"] == "inspect_code_execution_failure"
    assert bridge["repair_intent"]["mutation_allowed"] is False
    assert bridge["repair_intent"]["execution_allowed"] is False
    assert "requires confirmation" in bridge["reason"]


def test_runtime_repair_planner_bridge_allows_read_only_guided_plan():
    bridge = build_runtime_repair_planner_bridge(
        {
            "task_id": "task_002",
            "status": "failed",
            "repair_mode": "guided_repair_plan",
            "repair_scope": "verification",
            "repair_risk": "low",
            "requires_confirmation": False,
            "allowed_actions": [
                "inspect_runtime_state",
                "inspect_trace",
                "propose_repair_plan",
            ],
            "blocked_actions": [
                "schedule_task",
                "apply_patch",
                "write_file",
                "run_shell_command",
            ],
            "inspection_targets": ["result.json", "trace.json"],
            "suggestion_type": "inspect_verification_failure",
            "max_retry": 0,
        }
    )

    assert bridge["planner_allowed"] is True
    assert bridge["reason"] == "planner bridge may receive a read-only constrained repair intent"
    assert bridge["repair_intent"]["intent_type"] == "inspect_verification_failure"
    assert bridge["repair_intent"]["inspection_targets"] == ["result.json", "trace.json"]


def test_runtime_repair_planner_bridge_blocks_mutating_allowed_actions():
    bridge = build_runtime_repair_planner_bridge(
        {
            "repair_mode": "guided_repair_plan",
            "repair_scope": "verification",
            "repair_risk": "low",
            "requires_confirmation": False,
            "allowed_actions": ["propose_repair_plan", "write_file"],
            "blocked_actions": ["schedule_task"],
            "suggestion_type": "inspect_verification_failure",
        }
    )

    assert bridge["planner_allowed"] is False
    assert "mutating" in bridge["reason"]


def test_runtime_repair_planner_bridge_blocks_incomplete_boundary():
    bridge = build_runtime_repair_planner_bridge(
        {
            "repair_mode": "guided_repair_plan",
            "repair_scope": "verification",
            "repair_risk": "low",
            "requires_confirmation": False,
            "allowed_actions": ["propose_repair_plan"],
            "blocked_actions": ["apply_patch"],
            "suggestion_type": "inspect_verification_failure",
        }
    )

    assert bridge["planner_allowed"] is False
    assert "schedule_task is not blocked" in bridge["reason"]


def test_runtime_repair_planner_bridge_handles_no_repair_and_malformed_input():
    no_repair = build_runtime_repair_planner_bridge(
        {
            "repair_mode": "no_repair",
            "repair_scope": "read_only",
            "repair_risk": "low",
            "allowed_actions": ["inspect_runtime_state"],
            "blocked_actions": ["schedule_task"],
            "suggestion_type": "no_repair_needed",
        }
    )
    malformed = build_runtime_repair_planner_bridge(None)

    assert no_repair["planner_allowed"] is False
    assert no_repair["repair_intent"]["intent_type"] == "no_repair"
    assert malformed["ok"] is True
    assert malformed["planner_allowed"] is False
    assert malformed["raw_envelope"] is None


def test_runtime_repair_planner_bridges_accepts_single_or_list():
    single = build_runtime_repair_planner_bridges({"repair_mode": "observe_only"})
    many = build_runtime_repair_planner_bridges([
        {"repair_mode": "observe_only"},
        {"repair_mode": "no_repair"},
    ])

    assert len(single) == 1
    assert len(many) == 2
