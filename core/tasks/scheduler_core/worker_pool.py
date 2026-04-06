from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .task_scheduler_queue import ScheduledTask


@dataclass
class WorkerSlot:
    worker_id: str
    is_busy: bool = False
    task_id: Optional[str] = None
    started_at: Optional[float] = None


@dataclass
class RunningTaskRecord:
    worker_id: str
    task: ScheduledTask
    started_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "task": self.task.to_dict(),
            "started_at": self.started_at,
            "running_seconds": round(time.time() - self.started_at, 3),
        }


class WorkerPool:
    """
    WorkerPool 只負責：
    - worker slot 管理
    - running 任務占用情況
    - 完成後回收 slot

    不負責：
    - queue 排序
    - 真正執行任務
    - retry 決策
    """

    def __init__(self, max_workers: int = 1) -> None:
        if max_workers <= 0:
            raise ValueError("max_workers must be greater than 0")

        self._lock = threading.RLock()
        self._slots: Dict[str, WorkerSlot] = {
            f"worker-{i + 1}": WorkerSlot(worker_id=f"worker-{i + 1}")
            for i in range(max_workers)
        }
        self._running_by_worker: Dict[str, RunningTaskRecord] = {}
        self._running_by_task: Dict[str, RunningTaskRecord] = {}

    def capacity(self) -> int:
        return len(self._slots)

    def busy_count(self) -> int:
        with self._lock:
            return len(self._running_by_worker)

    def free_count(self) -> int:
        with self._lock:
            return len(self._slots) - len(self._running_by_worker)

    def has_free_slot(self) -> bool:
        return self.free_count() > 0

    def list_slots(self) -> List[Dict[str, Any]]:
        with self._lock:
            result: List[Dict[str, Any]] = []
            for slot in self._slots.values():
                running_seconds = None
                if slot.started_at is not None:
                    running_seconds = round(time.time() - slot.started_at, 3)

                result.append(
                    {
                        "worker_id": slot.worker_id,
                        "is_busy": slot.is_busy,
                        "task_id": slot.task_id,
                        "started_at": slot.started_at,
                        "running_seconds": running_seconds,
                    }
                )
            return result

    def list_running(self) -> List[Dict[str, Any]]:
        with self._lock:
            items = [record.to_dict() for record in self._running_by_worker.values()]
            items.sort(key=lambda x: x["started_at"])
            return items

    def get_running_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            record = self._running_by_task.get(task_id)
            return None if record is None else record.to_dict()

    def acquire(self, task: ScheduledTask) -> Optional[str]:
        with self._lock:
            if task.task_id in self._running_by_task:
                return None

            for worker_id, slot in self._slots.items():
                if not slot.is_busy:
                    slot.is_busy = True
                    slot.task_id = task.task_id
                    slot.started_at = time.time()

                    record = RunningTaskRecord(
                        worker_id=worker_id,
                        task=task,
                        started_at=slot.started_at,
                    )
                    self._running_by_worker[worker_id] = record
                    self._running_by_task[task.task_id] = record
                    return worker_id

            return None

    def assign(self, worker_id: str, task_id: str) -> bool:
        with self._lock:
            slot = self._slots.get(worker_id)
            if slot is None or slot.is_busy:
                return False

            fake_task = ScheduledTask(task_id=task_id, title=task_id)
            slot.is_busy = True
            slot.task_id = task_id
            slot.started_at = time.time()

            record = RunningTaskRecord(
                worker_id=worker_id,
                task=fake_task,
                started_at=slot.started_at,
            )
            self._running_by_worker[worker_id] = record
            self._running_by_task[task_id] = record
            return True

    def release(self, worker_id: str) -> Optional[RunningTaskRecord]:
        return self.release_by_worker(worker_id)

    def release_by_worker(self, worker_id: str) -> Optional[RunningTaskRecord]:
        with self._lock:
            record = self._running_by_worker.pop(worker_id, None)
            if record is None:
                return None

            self._running_by_task.pop(record.task.task_id, None)

            slot = self._slots.get(worker_id)
            if slot is not None:
                slot.is_busy = False
                slot.task_id = None
                slot.started_at = None

            return record

    def release_by_task(self, task_id: str) -> Optional[RunningTaskRecord]:
        with self._lock:
            record = self._running_by_task.get(task_id)
            if record is None:
                return None
            return self.release_by_worker(record.worker_id)

    def get_worker_for_task(self, task_id: str) -> Optional[str]:
        with self._lock:
            record = self._running_by_task.get(task_id)
            return None if record is None else record.worker_id

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "max_workers": len(self._slots),
                "busy_workers": len(self._running_by_worker),
                "free_workers": len(self._slots) - len(self._running_by_worker),
                "running_count": len(self._running_by_worker),
                "running_tasks": self.list_running(),
            }