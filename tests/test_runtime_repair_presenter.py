from __future__ import annotations

from core.display.runtime_repair_presenter import (
    format_runtime_repair_suggestion,
    format_runtime_repair_suggestions,
)


def test_format_runtime_repair_suggestion_accepts_prebuilt_suggestion():
    text = format_runtime_repair_suggestion(
        {
            "suggestion_type": "inspect_python_failure",
            "severity": "high",
            "reason": "python_failed; classification=fatal; attempts=3",
            "recommended_inspection": ["execution_log.json", "trace.json"],
            "retry_recommended": False,
            "human_summary": "Inspect logs before repairing code.",
            "task_id": "task_1",
            "status": "failed",
            "failed_event": {
                "action_type": "run_python",
                "status": "error",
                "error_type": "python_failed",
                "message": "python failed (code 1)",
                "classification": "fatal",
                "attempts": "3",
            },
        }
    )

    assert "Runtime Repair Suggestion:" in text
    assert "- task_id: task_1" in text
    assert "- type: inspect_python_failure" in text
    assert "- severity: high" in text
    assert "- retry_recommended: false" in text
    assert "execution_log.json" in text
    assert "action_type=run_python" in text
    assert "classification=fatal" in text


def test_format_runtime_repair_suggestion_builds_from_snapshot():
    text = format_runtime_repair_suggestion(
        {
            "task_id": "task_py",
            "status": "failed",
            "failed_events": [
                {
                    "source": "execution",
                    "event_type": "unknown_event",
                    "action_type": "run_python",
                    "status": "error",
                    "error": {
                        "type": "python_failed",
                        "message": "python failed (code 1)",
                        "classification": "fatal",
                        "max_attempts": 3,
                    },
                }
            ],
            "blockers": [],
            "latest_event": {},
        }
    )

    assert "- task_id: task_py" in text
    assert "- type: inspect_python_failure" in text
    assert "- severity: high" in text
    assert "- retry_recommended: false" in text
    assert "execution_log.json" in text
    assert "trace.json" in text
    assert "python_failed" in text


def test_format_runtime_repair_suggestion_handles_blocked_snapshot():
    text = format_runtime_repair_suggestion(
        {
            "task_id": "task_blocked",
            "status": "blocked",
            "failed_events": [],
            "blockers": ["waiting for approval"],
        }
    )

    assert "- type: blocked_task" in text
    assert "- severity: high" in text
    assert "waiting for approval" in text
    assert "runtime_state.json" in text


def test_format_runtime_repair_suggestion_handles_finished_snapshot():
    text = format_runtime_repair_suggestion(
        {
            "task_id": "task_done",
            "status": "finished",
            "failed_events": [],
            "blockers": [],
        }
    )

    assert "- type: no_repair_needed" in text
    assert "- severity: info" in text
    assert "- retry_recommended: false" in text
    assert "result.json" in text


def test_format_runtime_repair_suggestions_plural_wrapper():
    text = format_runtime_repair_suggestions({"task_id": "task_x", "status": "unknown"})

    assert "Runtime Repair Suggestion:" in text
    assert "- task_id: task_x" in text
