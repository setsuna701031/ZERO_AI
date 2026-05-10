from __future__ import annotations

import json

from core.tasks.runtime_repair_suggestion import (
    build_runtime_repair_suggestion,
    build_runtime_repair_suggestions,
)


def test_repair_suggestion_handles_malformed_snapshot():
    suggestion = build_runtime_repair_suggestion(None)

    assert suggestion["ok"] is True
    assert suggestion["suggestion_type"] == "insufficient_runtime_evidence"
    assert suggestion["severity"] == "low"
    assert suggestion["retry_recommended"] is False
    json.dumps(suggestion, ensure_ascii=False, default=str)


def test_repair_suggestion_for_blocked_task():
    suggestion = build_runtime_repair_suggestion(
        {
            "task_id": "task_1",
            "status": "blocked",
            "blockers": [{"reason": "approval required"}],
        }
    )

    assert suggestion["suggestion_type"] == "blocked_task"
    assert suggestion["severity"] == "high"
    assert suggestion["retry_recommended"] is False
    assert "approval required" in suggestion["reason"]
    assert "runtime_state.json" in suggestion["recommended_inspection"]


def test_repair_suggestion_for_python_failure_with_action_type():
    suggestion = build_runtime_repair_suggestion(
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
                        "retryable": False,
                    },
                }
            ],
        }
    )

    assert suggestion["suggestion_type"] == "inspect_python_failure"
    assert suggestion["severity"] == "high"
    assert suggestion["retry_recommended"] is False
    assert "python_failed" in suggestion["reason"]
    assert "attempts=3" in suggestion["reason"]
    assert "execution_log.json" in suggestion["recommended_inspection"]
    assert suggestion["failed_event"]["action_type"] == "run_python"


def test_repair_suggestion_for_verify_failure():
    suggestion = build_runtime_repair_suggestion(
        {
            "task_id": "task_verify",
            "status": "failed",
            "failed_events": [
                {
                    "action_type": "verify",
                    "status": "error",
                    "error": {
                        "type": "verification_failed",
                        "message": "expected output missing",
                    },
                }
            ],
        }
    )

    assert suggestion["suggestion_type"] == "inspect_verification_failure"
    assert suggestion["retry_recommended"] is False
    assert "result.json" in suggestion["recommended_inspection"]


def test_repair_suggestion_for_finished_task_needs_no_repair():
    suggestion = build_runtime_repair_suggestion(
        {
            "task_id": "task_done",
            "status": "finished",
            "failed_events": [],
            "blockers": [],
        }
    )

    assert suggestion["suggestion_type"] == "no_repair_needed"
    assert suggestion["severity"] == "info"
    assert suggestion["retry_recommended"] is False


def test_repair_suggestion_for_running_task_observes_latest_event():
    suggestion = build_runtime_repair_suggestion(
        {
            "task_id": "task_run",
            "status": "running",
            "latest_event": {"action_type": "run_command", "summary": "command executing"},
        }
    )

    assert suggestion["suggestion_type"] == "observe_running_task"
    assert suggestion["retry_recommended"] is False
    assert "run_command" in suggestion["human_summary"]


def test_repair_suggestions_list_wrapper():
    suggestions = build_runtime_repair_suggestions({"status": "finished"})

    assert isinstance(suggestions, list)
    assert len(suggestions) == 1
    assert suggestions[0]["suggestion_type"] == "no_repair_needed"
