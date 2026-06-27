from __future__ import annotations

import copy
from typing import Any, Dict, List

from core.tasks.scheduler_core.repo_blocked_state import (
    _append_status_to_history,
    _downgrade_advisory_blocked_status,
    _has_remaining_steps,
    _is_successful_nonblocking_step_result,
    _should_downgrade_advisory_blocked_status,
    sync_blocked_state,
    sync_unblocked_state,
)


class WorkerPool:
    def __init__(self) -> None:
        self.released: List[str] = []

    def release_by_task(self, task_id: str) -> None:
        self.released.append(task_id)


class Scheduler:
    SCHEDULER_BUILD = "test-build"
    STATUS_BLOCKED = "blocked"
    STATUS_QUEUED = "queued"
    TERMINAL_STATUSES = {"finished", "failed"}

    def __init__(self, task: Dict[str, Any]) -> None:
        self.task = task
        self.current_tick = 5
        self.worker_pool = WorkerPool()
        self.persisted: List[Dict[str, Any]] = []
        self.traces: List[Dict[str, Any]] = []

    def _get_task_from_repo(self, task_id: str) -> Dict[str, Any]:
        return self.task if task_id == self.task.get("task_id") else {}

    def _append_history(self, history: Any, status: str) -> List[str]:
        items = list(history) if isinstance(history, list) else []
        items.append(status)
        return items

    def _persist_task_payload(self, task_id: str, task: Dict[str, Any]) -> None:
        self.persisted.append(copy.deepcopy(task))

    def _load_trace_for_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return {"events": []}

    def _trace_status(self, **kwargs: Any) -> None:
        kwargs["trace"]["events"].append(copy.deepcopy(kwargs))

    def _save_trace_for_task(self, task: Dict[str, Any], trace: Dict[str, Any]) -> None:
        self.traces.append(copy.deepcopy(trace))


def test_advisory_blocked_status_downgrades_when_success_has_remaining_steps() -> None:
    payload = {
        "status": "blocked",
        "blocked_reason": "observe only transition evidence",
        "last_step_result": {"ok": True},
        "current_step_index": 1,
        "steps_total": 2,
        "history": ["running"],
    }

    assert _is_successful_nonblocking_step_result(payload["last_step_result"]) is True
    assert _has_remaining_steps(payload) is True
    assert _should_downgrade_advisory_blocked_status(payload) is True

    downgraded = _downgrade_advisory_blocked_status(payload)

    assert downgraded["status"] == "queued"
    assert downgraded["blocked_reason"] == ""
    assert downgraded["history"] == ["running", "queued"]
    assert payload["status"] == "blocked"


def test_append_status_to_history_deduplicates_tail_status() -> None:
    assert _append_status_to_history(["running", "queued"], "queued") == ["running", "queued"]
    assert _append_status_to_history(["running"], "queued") == ["running", "queued"]


def test_sync_blocked_state_persists_and_traces_blocked_task() -> None:
    scheduler = Scheduler({"task_id": "task-1", "status": "running", "history": [], "last_error": "old"})

    sync_blocked_state(scheduler, "task-1", "waiting")

    assert scheduler.task["status"] == "blocked"
    assert scheduler.task["blocked_reason"] == "waiting"
    assert scheduler.task["last_error"] == ""
    assert scheduler.persisted[-1]["status"] == "blocked"
    assert scheduler.worker_pool.released == ["task-1"]
    assert scheduler.traces[-1]["events"][-1]["status"] == "blocked"


def test_sync_unblocked_state_requeues_blocked_task() -> None:
    scheduler = Scheduler(
        {
            "task_id": "task-1",
            "status": "blocked",
            "history": ["blocked"],
            "blocked_reason": "waiting",
            "last_error": "old",
            "failure_message": "old",
        }
    )

    sync_unblocked_state(scheduler, "task-1")

    assert scheduler.task["status"] == "queued"
    assert scheduler.task["blocked_reason"] == ""
    assert scheduler.task["last_error"] == ""
    assert scheduler.task["failure_message"] == ""
    assert scheduler.persisted[-1]["status"] == "queued"
