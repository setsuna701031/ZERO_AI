from core.display.runtime_repair_envelope_presenter import (
    format_runtime_repair_envelope,
)


def test_runtime_repair_envelope_presenter_formats_fields():
    envelope = {
        "task_id": "task_001",
        "status": "failed",
        "repair_mode": "manual_review",
        "repair_scope": "code",
        "repair_risk": "high",
        "suggestion_type": "inspect_python_failure",
        "severity": "high",
        "retry_recommended": False,
        "requires_confirmation": True,
        "max_retry": 0,
        "reason": "python_failed",
        "human_summary": "repair envelope generated",
        "allowed_actions": [
            "inspect_trace",
            "inspect_execution_log",
        ],
        "blocked_actions": [
            "write_file",
            "apply_patch",
        ],
        "inspection_targets": [
            "trace.json",
            "execution_log.json",
        ],
    }

    text = format_runtime_repair_envelope(envelope)

    assert "Runtime Repair Envelope:" in text

    assert "task_id: task_001" in text
    assert "repair_mode: manual_review" in text
    assert "repair_scope: code" in text
    assert "repair_risk: high" in text

    assert "allowed_actions:" in text
    assert "inspect_trace" in text

    assert "blocked_actions:" in text
    assert "write_file" in text

    assert "inspection_targets:" in text
    assert "trace.json" in text


def test_runtime_repair_envelope_presenter_handles_invalid_input():
    text = format_runtime_repair_envelope(None)

    assert "Runtime Repair Envelope:" in text