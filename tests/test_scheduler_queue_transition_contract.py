from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from core.tasks.scheduler_core.queue_sync_helpers import enqueue_repo_task_if_ready


class RecordingQueue:
    def __init__(self) -> None:
        self.items: Dict[str, Any] = {}
        self.enqueued: List[str] = []
        self.removed: List[str] = []

    def enqueue(self, scheduled_task: Any, overwrite: bool = False) -> bool:
        task_id = str(getattr(scheduled_task, "task_id", "") or "")
        if task_id in self.items and not overwrite:
            return False
        self.items[task_id] = scheduled_task
        self.enqueued.append(task_id)
        return True

    def remove(self, task_id: str) -> None:
        self.items.pop(task_id, None)
        self.removed.append(task_id)

    def contains(self, task_id: str) -> bool:
        return task_id in self.items


class RecordingWorkerPool:
    def __init__(self) -> None:
        self.running: Dict[str, Any] = {}
        self.released: List[str] = []

    def get_running_task(self, task_id: str) -> Optional[Any]:
        return self.running.get(task_id)

    def release_by_task(self, task_id: str) -> None:
        self.released.append(task_id)


class QueueTransitionScheduler:
    TERMINAL_STATUSES = {"finished", "done", "success", "completed", "failed", "error", "cancelled"}
    READY_STATUSES = {"queued", "ready", "retry", "retrying"}
    STATUS_BLOCKED = "blocked"

    def __init__(self, tasks: List[Dict[str, Any]]) -> None:
        self.tasks = {str(task.get("task_id")): task for task in tasks}
        self.scheduler_queue = RecordingQueue()
        self.worker_pool = RecordingWorkerPool()
        self.blocked_syncs: List[Dict[str, str]] = []
        self.unblocked_syncs: List[str] = []
        self.repo_task_mark_callbacks: Dict[str, Any] = {
            "mark_queued": self._record_mark_callback,
        }
        self.mark_callback_calls: List[Dict[str, Any]] = []

    def _record_mark_callback(self, **kwargs: Any) -> None:
        self.mark_callback_calls.append(kwargs)

    def _hydrate_task_from_workspace(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return task

    def _extract_task_id(self, task: Dict[str, Any]) -> str:
        return str(task.get("task_id") or "").strip()

    def _task_dependencies_satisfied(self, task: Dict[str, Any]) -> tuple[bool, str]:
        if task.get("deps_ready") is False:
            return False, str(task.get("blocked_reason") or "waiting dependency")
        return True, ""

    def _sync_blocked_state(self, task_id: str, blocked_reason: str) -> None:
        self.blocked_syncs.append({"task_id": task_id, "blocked_reason": blocked_reason})
        task = self.tasks.get(task_id)
        if isinstance(task, dict):
            task["status"] = self.STATUS_BLOCKED
            task["blocked_reason"] = blocked_reason

    def _sync_unblocked_state(self, task_id: str) -> None:
        self.unblocked_syncs.append(task_id)
        task = self.tasks.get(task_id)
        if isinstance(task, dict):
            task["status"] = "queued"
            task["blocked_reason"] = ""

    def _get_task_from_repo(self, task_id: str) -> Optional[Dict[str, Any]]:
        return self.tasks.get(task_id)

    def _queue_contains_task(self, task_id: str) -> bool:
        return self.scheduler_queue.contains(task_id)

    def _repo_task_to_scheduled_task(self, task: Dict[str, Any]) -> Any:
        return SimpleNamespace(
            task_id=self._extract_task_id(task),
            priority=int(task.get("priority", 0) or 0),
            payload=copy.deepcopy(task),
        )


def _enqueue(scheduler: QueueTransitionScheduler, task: Dict[str, Any], overwrite: bool = False) -> bool:
    return enqueue_repo_task_if_ready(
        scheduler=scheduler,
        task=task,
        overwrite=overwrite,
        terminal_statuses=scheduler.TERMINAL_STATUSES,
        ready_statuses=scheduler.READY_STATUSES,
        status_blocked=scheduler.STATUS_BLOCKED,
    )


def test_finished_task_is_not_requeued() -> None:
    task = {"task_id": "task-1", "status": "finished"}
    scheduler = QueueTransitionScheduler([task])
    scheduler.scheduler_queue.items["task-1"] = SimpleNamespace(task_id="task-1")

    assert _enqueue(scheduler, task, overwrite=True) is False
    assert scheduler.scheduler_queue.contains("task-1") is False
    assert scheduler.scheduler_queue.enqueued == []
    assert scheduler.worker_pool.released == ["task-1"]


def test_failed_terminal_task_is_not_requeued() -> None:
    task = {"task_id": "task-1", "status": "failed"}
    scheduler = QueueTransitionScheduler([task])
    scheduler.scheduler_queue.items["task-1"] = SimpleNamespace(task_id="task-1")

    assert _enqueue(scheduler, task, overwrite=True) is False
    assert scheduler.scheduler_queue.contains("task-1") is False
    assert scheduler.scheduler_queue.enqueued == []
    assert scheduler.worker_pool.released == ["task-1"]


def test_blocked_dependency_task_stays_blocked() -> None:
    task = {
        "task_id": "task-1",
        "status": "blocked",
        "deps_ready": False,
        "blocked_reason": "waiting dependency: dep-1",
    }
    scheduler = QueueTransitionScheduler([task])
    scheduler.scheduler_queue.items["task-1"] = SimpleNamespace(task_id="task-1")

    assert _enqueue(scheduler, task, overwrite=True) is False
    assert scheduler.tasks["task-1"]["status"] == "blocked"
    assert scheduler.tasks["task-1"]["blocked_reason"] == "waiting dependency: dep-1"
    assert scheduler.scheduler_queue.contains("task-1") is False
    assert scheduler.blocked_syncs == [
        {"task_id": "task-1", "blocked_reason": "waiting dependency: dep-1"}
    ]


def test_ready_and_queued_tasks_remain_dispatchable() -> None:
    ready = {"task_id": "ready-task", "status": "ready"}
    queued = {"task_id": "queued-task", "status": "queued"}
    scheduler = QueueTransitionScheduler([ready, queued])

    assert _enqueue(scheduler, ready, overwrite=True) is True
    assert _enqueue(scheduler, queued, overwrite=True) is True
    assert scheduler.scheduler_queue.contains("ready-task") is True
    assert scheduler.scheduler_queue.contains("queued-task") is True
    assert scheduler.scheduler_queue.enqueued == ["ready-task", "queued-task"]


def test_repo_task_mark_adapter_does_not_change_queue_transition_behavior() -> None:
    finished = {"task_id": "finished-task", "status": "finished"}
    queued = {"task_id": "queued-task", "status": "queued"}
    scheduler = QueueTransitionScheduler([finished, queued])
    scheduler.scheduler_queue.items["finished-task"] = SimpleNamespace(task_id="finished-task")

    assert _enqueue(scheduler, finished, overwrite=True) is False
    assert _enqueue(scheduler, queued, overwrite=True) is True
    assert scheduler.scheduler_queue.contains("finished-task") is False
    assert scheduler.scheduler_queue.contains("queued-task") is True
    assert scheduler.mark_callback_calls == []
