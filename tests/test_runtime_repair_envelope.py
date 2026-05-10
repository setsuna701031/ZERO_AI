from __future__ import annotations

from core.tasks.runtime_repair_envelope import (
    build_runtime_repair_envelope,
    build_runtime_repair_envelopes,
)


def test_repair_envelope_handles_empty_input_as_read_only_unknown():
    envelope = build_runtime_repair_envelope(None)

    assert envelope["ok"] is True
    assert envelope["suggestion_type"] == "unknown_suggestion"
    assert envelope["repair_scope"] == "unknown"
    assert envelope["repair_risk"] == "high"
    assert envelope["repair_mode"] == "manual_review"
    assert envelope["requires_confirmation"] is True
    assert envelope["max_retry"] == 0
    assert "execute_repair" in envelope["blocked_actions"]


def test_no_repair_suggestion_produces_observation_envelope():
    envelope = build_runtime_repair_envelope(
        {
            "suggestion_type": "no_repair_needed",
            "severity": "info",
            "task_id": "task_done",
            "status": "finished",
            "recommended_inspection": ["result.json"],
        }
    )

    assert envelope["task_id"] == "task_done"
    assert envelope["repair_scope"] == "read_only"
    assert envelope["repair_risk"] == "low"
    assert envelope["repair_mode"] == "no_repair"
    assert envelope["requires_confirmation"] is False
    assert envelope["inspection_targets"] == ["result.json"]
    assert envelope["allowed_actions"] == [
        "inspect_runtime_state",
        "inspect_execution_log",
        "inspect_trace",
    ]


def test_python_failure_high_severity_requires_manual_review_and_blocks_mutation():
    envelope = build_runtime_repair_envelope(
        {
            "suggestion_type": "inspect_python_failure",
            "severity": "high",
            "reason": "python_failed; classification=fatal; attempts=3",
            "retry_recommended": False,
            "recommended_inspection": ["execution_log.json", "trace.json"],
            "task_id": "task_py",
            "status": "finished",
        }
    )

    assert envelope["repair_scope"] == "code"
    assert envelope["repair_risk"] == "high"
    assert envelope["repair_mode"] == "manual_review"
    assert envelope["requires_confirmation"] is True
    assert envelope["max_retry"] == 0
    assert "prepare_code_repair" in envelope["allowed_actions"]
    assert "auto_repair" in envelope["blocked_actions"]
    assert "apply_patch" in envelope["blocked_actions"]


def test_retryable_low_risk_file_failure_allows_limited_guided_plan():
    envelope = build_runtime_repair_envelope(
        {
            "suggestion_type": "inspect_file_operation_failure",
            "severity": "low",
            "retry_recommended": True,
            "recommended_inspection": ["execution_log.json"],
            "task_id": "task_file",
            "status": "failed",
        },
        {
            "repair_scope": "workspace_shared",
            "repair_risk": "low",
        },
    )

    assert envelope["repair_scope"] == "workspace_shared"
    assert envelope["repair_risk"] == "low"
    assert envelope["repair_mode"] == "guided_repair_plan"
    assert envelope["requires_confirmation"] is True
    assert envelope["max_retry"] == 2
    assert "propose_repair_plan" in envelope["allowed_actions"]
    assert "auto_repair_without_confirmation" in envelope["blocked_actions"]


def test_contract_can_override_actions_confirmation_and_budget():
    envelope = build_runtime_repair_envelope(
        {
            "suggestion_type": "inspect_runtime_failure",
            "severity": "medium",
            "retry_recommended": True,
        },
        {
            "repair_scope": "workspace_shared",
            "repair_risk": "medium",
            "max_retry": 3,
            "requires_confirmation": False,
            "allowed_actions": ["inspect_trace", "propose_repair_plan", "inspect_trace"],
            "blocked_actions": ["network_access"],
        },
    )

    assert envelope["max_retry"] == 3
    assert envelope["requires_confirmation"] is False
    assert envelope["allowed_actions"] == ["inspect_trace", "propose_repair_plan"]
    assert "network_access" in envelope["blocked_actions"]


def test_build_runtime_repair_envelopes_accepts_single_or_list():
    single = build_runtime_repair_envelopes({"suggestion_type": "observe_running_task"})
    multiple = build_runtime_repair_envelopes([
        {"suggestion_type": "observe_running_task"},
        {"suggestion_type": "inspect_verification_failure", "severity": "medium"},
    ])

    assert len(single) == 1
    assert single[0]["repair_mode"] == "observe_only"
    assert len(multiple) == 2
    assert multiple[1]["repair_scope"] == "verification"
