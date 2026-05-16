from __future__ import annotations

from core.tasks.scheduler_core.public_task_record_helpers import normalize_public_status_fields
from core.tasks.scheduler_core.queue_formatting_helpers import (
    build_queue_rows_payload,
    build_queue_snapshot_payload,
    is_review_queue_task,
)


class FakeDispatcher:
    def __init__(self) -> None:
        self.queued = [
            {
                "task_id": "task_1",
                "status": "queued",
                "priority": 5,
                "current_step_index": 2,
                "extra": "not exposed in rows",
            }
        ]
        self.running = [{"task_id": "task_2", "status": "running"}]

    def list_queued(self):
        return list(self.queued)

    def list_running(self):
        return list(self.running)


class FakeWorkerPool:
    def stats(self):
        return {"slots": 1, "running": 1}


def test_build_queue_rows_payload_formats_public_rows_only() -> None:
    payload = build_queue_rows_payload(
        dispatcher=FakeDispatcher(),
        scheduler_build="test-build",
        current_tick=7,
    )

    assert payload == {
        "ok": True,
        "scheduler_build": "test-build",
        "tick": 7,
        "count": 1,
        "rows": [
            {
                "task_id": "task_1",
                "status": "queued",
                "priority": 5,
                "current_step_index": 2,
            }
        ],
    }


def test_is_review_queue_task_filters_pending_and_closed_reviews() -> None:
    assert is_review_queue_task({"requires_review": True}, review_required_status="review_required")
    assert is_review_queue_task({"review_status": "pending"}, review_required_status="review_required")
    assert is_review_queue_task({"status": "review_required"}, review_required_status="review_required")
    assert not is_review_queue_task(
        {"requires_review": True, "review_status": "approved"},
        review_required_status="review_required",
    )


def test_build_queue_snapshot_payload_formats_snapshot_without_mutating_state() -> None:
    repo_tasks = [
        {"task_id": "task_1", "status": "queued"},
        {"task_id": "task_review", "review_status": "pending"},
    ]

    payload = build_queue_snapshot_payload(
        dispatcher=FakeDispatcher(),
        worker_pool=FakeWorkerPool(),
        repo_tasks=repo_tasks,
        scheduler_build="test-build",
        current_tick=9,
        review_required_status="review_required",
        workspace_dir="workspace",
        workspace_root="/repo/workspace",
        shared_dir="/repo/workspace/shared",
    )

    assert payload["ok"] is True
    assert payload["ready_queue_size"] == 1
    assert payload["running_count"] == 1
    assert payload["review_queue"] == [{"task_id": "task_review", "review_status": "pending"}]
    assert payload["review_queue_size"] == 1
    assert payload["worker_pool"] == {"slots": 1, "running": 1}
    assert payload["task_count"] == 2


def test_normalize_public_status_fields_formats_current_step_and_state_detail() -> None:
    task = normalize_public_status_fields(
        {
            "status": "blocked",
            "blocked_reason": "waiting for dependency",
            "current_step_index": 99,
            "steps": [{"type": "read_file"}],
        },
        status_blocked="blocked",
        status_review_required="review_required",
    )

    assert task["current_step_index"] == 0
    assert task["current_step"] == {"type": "read_file"}
    assert task["steps_total"] == 1
    assert task["state_detail"] == "waiting for dependency"
