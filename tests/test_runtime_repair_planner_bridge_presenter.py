from core.display.runtime_repair_planner_bridge_presenter import (
    format_runtime_repair_planner_bridge,
)


def test_runtime_repair_planner_bridge_presenter_formats_gate_fields():
    bridge = {
        "task_id": "task_001",
        "status": "failed",
        "bridge_mode": "read_only_planner_gate",
        "planner_allowed": False,
        "requires_confirmation": True,
        "repair_mode": "manual_review",
        "repair_scope": "code_execution_review",
        "repair_risk": "high",
        "max_retry": 0,
        "reason": "scope requires confirmation",
        "human_summary": "Planner bridge is blocked.",
        "repair_intent": {
            "intent_type": "inspect_code_execution_failure",
            "source": "runtime_repair_envelope",
            "scope": "code_execution_review",
            "risk": "high",
            "mode": "manual_review",
            "allowed_actions": ["inspect_trace", "inspect_execution_log"],
            "inspection_targets": ["trace.json", "execution_log.json"],
            "mutation_allowed": False,
            "execution_allowed": False,
        },
        "allowed_actions": ["inspect_trace"],
        "blocked_actions": ["schedule_task", "apply_patch"],
        "inspection_targets": ["trace.json"],
    }

    text = format_runtime_repair_planner_bridge(bridge)

    assert "Runtime Repair Planner Bridge:" in text
    assert "task_id: task_001" in text
    assert "planner_allowed: False" in text
    assert "requires_confirmation: True" in text
    assert "repair_intent:" in text
    assert "inspect_code_execution_failure" in text
    assert "mutation_allowed: False" in text
    assert "blocked_actions:" in text
    assert "schedule_task" in text


def test_runtime_repair_planner_bridge_presenter_handles_invalid_input():
    text = format_runtime_repair_planner_bridge(None)

    assert "Runtime Repair Planner Bridge:" in text
