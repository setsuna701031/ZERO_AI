from core.tasks.scheduler_core.repo_observability import build_failure_observability_event


def test_build_failure_observability_event_ok_default() -> None:
    event = build_failure_observability_event(
        event_type="repo_task_requeued",
        task={"id": "task-a", "status": "queued"},
    )

    assert event["event_type"] == "repo_task_requeued"
    assert event["ok"] is True
    assert event["task_id"] == "task-a"
    assert event["status"] == "queued"
    assert event["failure_type"] == "repo_task_requeued"
    assert event["runtime_mode"] == "repo_state"


def test_build_failure_observability_event_failed_default() -> None:
    event = build_failure_observability_event(
        event_type="repo_task_failure",
        task={"task_id": "task-b", "status": "failed", "last_error": "boom"},
    )

    assert event["ok"] is False
    assert event["task_id"] == "task-b"
    assert event["status"] == "failed"
    assert event["failure_type"] == "repo_task_failed"
    assert event["error_text"] == "boom"


def test_build_failure_observability_event_prefers_explicit_values() -> None:
    event = build_failure_observability_event(
        event_type="custom_event",
        task={
            "task_id": "task-inner",
            "status": "failed",
            "failure_message": "inner",
            "failure_type": "inner_type",
            "retry_count": 2,
            "replan_count": 3,
            "repair_fingerprint": "fp-1",
        },
        task_id="task-explicit",
        error_text="explicit error",
        status="error",
    )

    assert event["event_type"] == "custom_event"
    assert event["ok"] is False
    assert event["task_id"] == "task-explicit"
    assert event["status"] == "error"
    assert event["failure_type"] == "inner_type"
    assert event["error_text"] == "explicit error"
    assert event["retry_count"] == 2
    assert event["replan_count"] == 3
    assert event["repair_fingerprint"] == "fp-1"
