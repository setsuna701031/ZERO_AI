from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .task_scheduler_queue import (
    STATUS_FAILED,
    STATUS_FINISHED,
    STATUS_QUEUED,
    ScheduledTask,
    TaskSchedulerQueue,
)
from .worker_pool import WorkerPool


@dataclass
class DispatchResult:
    dispatched: bool
    worker_id: Optional[str] = None
    task: Optional[ScheduledTask] = None
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dispatched": self.dispatched,
            "worker_id": self.worker_id,
            "task": None if self.task is None else self.task.to_dict(),
            "reason": self.reason,
        }


class TaskDispatcher:
    """
    TaskDispatcher 只負責：
    - 從 queue 取出任務
    - 檢查 worker slot
    - 把任務派發進 running 狀態

    不負責：
    - 真正執行 task payload
    - planner / executor 細節
    - queue 的排序演算法
    """

    def __init__(
        self,
        queue: TaskSchedulerQueue,
        worker_pool: WorkerPool,
    ) -> None:
        self.queue = queue
        self.worker_pool = worker_pool

    def dispatch_once(self) -> DispatchResult:
        if not self.worker_pool.has_free_slot():
            return DispatchResult(
                dispatched=False,
                reason="no_free_worker_slot",
            )

        next_task = self.queue.pop_next()
        if next_task is None:
            return DispatchResult(
                dispatched=False,
                reason="no_queued_task",
            )

        worker_id = self.worker_pool.acquire(next_task)
        if worker_id is None:
            self.queue.requeue(next_task.task_id, priority=next_task.priority)
            return DispatchResult(
                dispatched=False,
                reason="worker_acquire_failed",
            )

        return DispatchResult(
            dispatched=True,
            worker_id=worker_id,
            task=next_task,
            reason=None,
        )

    def dispatch_until_full(self) -> List[DispatchResult]:
        results: List[DispatchResult] = []

        while self.worker_pool.has_free_slot():
            result = self.dispatch_once()
            if not result.dispatched:
                break
            results.append(result)

        return results

    def complete_task(
        self,
        task_id: str,
        result: Any = None,
    ) -> bool:
        running = self.worker_pool.get_running_task(task_id)
        if running is None:
            return False

        released = self.worker_pool.release_by_task(task_id)
        if released is None:
            return False

        return self.queue.mark_finished(task_id, result=result)

    def fail_task(
        self,
        task_id: str,
        error: str,
        requeue_on_retry: bool = True,
    ) -> Dict[str, Any]:
        running = self.worker_pool.get_running_task(task_id)
        if running is None:
            return {
                "ok": False,
                "reason": "task_not_running",
            }

        released = self.worker_pool.release_by_task(task_id)
        if released is None:
            return {
                "ok": False,
                "reason": "worker_release_failed",
            }

        task = self.queue.get_task(task_id)
        if task is None:
            return {
                "ok": False,
                "reason": "task_not_found_in_queue_storage",
            }

        self.queue.increment_retry(task_id)
        task = self.queue.get_task(task_id)
        if task is None:
            return {
                "ok": False,
                "reason": "task_not_found_after_retry_increment",
            }

        should_retry = requeue_on_retry and (task.retry_count <= task.max_retries)

        if should_retry:
            self.queue.requeue(
                task_id=task_id,
                priority=task.priority,
                error=error,
            )
            return {
                "ok": True,
                "final_status": STATUS_QUEUED,
                "retry_count": task.retry_count,
                "max_retries": task.max_retries,
                "requeued": True,
            }

        self.queue.mark_failed(task_id, error=error)
        return {
            "ok": True,
            "final_status": STATUS_FAILED,
            "retry_count": task.retry_count,
            "max_retries": task.max_retries,
            "requeued": False,
        }

    def snapshot(self) -> Dict[str, Any]:
        return {
            "queue": self.queue.stats(),
            "workers": self.worker_pool.stats(),
        }

    def list_queued(self) -> List[Dict[str, Any]]:
        return [task.to_dict() for task in self.queue.list_queued()]

    def list_running(self) -> List[Dict[str, Any]]:
        return self.worker_pool.list_running()

    def list_all_tasks(self) -> List[Dict[str, Any]]:
        return [task.to_dict() for task in self.queue.list_all()]