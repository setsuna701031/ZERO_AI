from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


QUEUE_STATUS_PENDING = "pending"
QUEUE_STATUS_RUNNING = "running"
QUEUE_STATUS_PAUSED = "paused"
QUEUE_STATUS_FINISHED = "finished"
QUEUE_STATUS_FAILED = "failed"
QUEUE_STATUS_CANCELLED = "cancelled"


VALID_QUEUE_STATUSES = {
    QUEUE_STATUS_PENDING,
    QUEUE_STATUS_RUNNING,
    QUEUE_STATUS_PAUSED,
    QUEUE_STATUS_FINISHED,
    QUEUE_STATUS_FAILED,
    QUEUE_STATUS_CANCELLED,
}


@dataclass
class QueueTask:
    queue_task_id: str
    goal: str
    source_task_name: str = ""
    priority: int = 100
    status: str = QUEUE_STATUS_PENDING
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    started_at: str = ""
    finished_at: str = ""
    run_mode: str = "normal"
    task_type: str = "general"
    assigned_task_name: str = ""
    error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QueueTask":
        return cls(
            queue_task_id=str(data.get("queue_task_id", "")).strip(),
            goal=str(data.get("goal", "")).strip(),
            source_task_name=str(data.get("source_task_name", "")).strip(),
            priority=int(data.get("priority", 100)),
            status=str(data.get("status", QUEUE_STATUS_PENDING)).strip(),
            created_at=str(data.get("created_at", utc_now_iso())).strip(),
            updated_at=str(data.get("updated_at", utc_now_iso())).strip(),
            started_at=str(data.get("started_at", "")).strip(),
            finished_at=str(data.get("finished_at", "")).strip(),
            run_mode=str(data.get("run_mode", "normal")).strip(),
            task_type=str(data.get("task_type", "general")).strip(),
            assigned_task_name=str(data.get("assigned_task_name", "")).strip(),
            error=str(data.get("error", "")).strip(),
            metadata=data.get("metadata", {}) or {},
        )


class TaskQueue:
    """
    Persistent task queue.

    Features:
    - enqueue task
    - list tasks
    - get next runnable task
    - mark running / finished / failed / paused / cancelled
    - reprioritize
    - resume paused task
    - persist to queue.json
    """

    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root)
        self.system_dir = self.workspace_root / "_system"
        self.system_dir.mkdir(parents=True, exist_ok=True)

        self.queue_file = self.system_dir / "task_queue.json"
        self._lock = threading.RLock()
        self._tasks: List[QueueTask] = []
        self._load()

    # -------------------------------------------------------------------------
    # persistence
    # -------------------------------------------------------------------------
    def _load(self) -> None:
        with self._lock:
            if not self.queue_file.exists():
                self._tasks = []
                self._save()
                return

            try:
                raw = json.loads(self.queue_file.read_text(encoding="utf-8"))
                items = raw.get("tasks", [])
                self._tasks = [QueueTask.from_dict(item) for item in items]
            except Exception:
                self._tasks = []
                self._save()

    def _save(self) -> None:
        with self._lock:
            data = {
                "updated_at": utc_now_iso(),
                "tasks": [task.to_dict() for task in self._tasks],
            }
            self.queue_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    # -------------------------------------------------------------------------
    # helpers
    # -------------------------------------------------------------------------
    def _find_index(self, queue_task_id: str) -> int:
        for idx, task in enumerate(self._tasks):
            if task.queue_task_id == queue_task_id:
                return idx
        return -1

    def _get_task_or_raise(self, queue_task_id: str) -> QueueTask:
        idx = self._find_index(queue_task_id)
        if idx < 0:
            raise ValueError(f"queue task not found: {queue_task_id}")
        return self._tasks[idx]

    def _touch(self, task: QueueTask) -> None:
        task.updated_at = utc_now_iso()

    def _sorted_pending(self) -> List[QueueTask]:
        pending = [t for t in self._tasks if t.status == QUEUE_STATUS_PENDING]
        pending.sort(key=lambda x: (x.priority, x.created_at, x.queue_task_id))
        return pending

    def _sorted_all(self) -> List[QueueTask]:
        items = list(self._tasks)
        items.sort(key=lambda x: (x.priority, x.created_at, x.queue_task_id))
        return items

    # -------------------------------------------------------------------------
    # public api
    # -------------------------------------------------------------------------
    def enqueue(
        self,
        goal: str,
        *,
        priority: int = 100,
        source_task_name: str = "",
        run_mode: str = "normal",
        task_type: str = "general",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> QueueTask:
        goal = (goal or "").strip()
        if not goal:
            raise ValueError("goal cannot be empty")

        queue_task = QueueTask(
            queue_task_id=f"qtask_{uuid.uuid4().hex[:12]}",
            goal=goal,
            source_task_name=source_task_name.strip(),
            priority=int(priority),
            status=QUEUE_STATUS_PENDING,
            run_mode=run_mode.strip() or "normal",
            task_type=task_type.strip() or "general",
            metadata=metadata or {},
        )

        with self._lock:
            self._tasks.append(queue_task)
            self._save()
            return queue_task

    def list_tasks(
        self,
        *,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            items = self._sorted_all()
            if status:
                status = status.strip()
                items = [t for t in items if t.status == status]
            if limit is not None and limit >= 0:
                items = items[:limit]
            return [t.to_dict() for t in items]

    def get_task(self, queue_task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            idx = self._find_index(queue_task_id)
            if idx < 0:
                return None
            return self._tasks[idx].to_dict()

    def get_next_runnable_task(self) -> Optional[QueueTask]:
        with self._lock:
            # 單機版先限制同時間只跑一個 running task
            has_running = any(t.status == QUEUE_STATUS_RUNNING for t in self._tasks)
            if has_running:
                return None

            pending = self._sorted_pending()
            if not pending:
                return None
            return pending[0]

    def mark_running(self, queue_task_id: str, assigned_task_name: str = "") -> Dict[str, Any]:
        with self._lock:
            task = self._get_task_or_raise(queue_task_id)
            if task.status not in {QUEUE_STATUS_PENDING, QUEUE_STATUS_PAUSED}:
                raise ValueError(
                    f"cannot mark running from status '{task.status}'"
                )

            task.status = QUEUE_STATUS_RUNNING
            task.started_at = task.started_at or utc_now_iso()
            task.assigned_task_name = assigned_task_name.strip()
            self._touch(task)
            self._save()
            return task.to_dict()

    def mark_finished(self, queue_task_id: str, assigned_task_name: str = "") -> Dict[str, Any]:
        with self._lock:
            task = self._get_task_or_raise(queue_task_id)
            if task.status not in {QUEUE_STATUS_RUNNING, QUEUE_STATUS_PENDING, QUEUE_STATUS_PAUSED}:
                raise ValueError(
                    f"cannot mark finished from status '{task.status}'"
                )

            task.status = QUEUE_STATUS_FINISHED
            task.finished_at = utc_now_iso()
            if assigned_task_name.strip():
                task.assigned_task_name = assigned_task_name.strip()
            self._touch(task)
            self._save()
            return task.to_dict()

    def mark_failed(
        self,
        queue_task_id: str,
        error: str = "",
        assigned_task_name: str = "",
    ) -> Dict[str, Any]:
        with self._lock:
            task = self._get_task_or_raise(queue_task_id)
            if task.status not in {QUEUE_STATUS_RUNNING, QUEUE_STATUS_PENDING, QUEUE_STATUS_PAUSED}:
                raise ValueError(
                    f"cannot mark failed from status '{task.status}'"
                )

            task.status = QUEUE_STATUS_FAILED
            task.finished_at = utc_now_iso()
            task.error = (error or "").strip()
            if assigned_task_name.strip():
                task.assigned_task_name = assigned_task_name.strip()
            self._touch(task)
            self._save()
            return task.to_dict()

    def pause_task(self, queue_task_id: str) -> Dict[str, Any]:
        with self._lock:
            task = self._get_task_or_raise(queue_task_id)
            if task.status != QUEUE_STATUS_RUNNING:
                raise ValueError(f"only running task can be paused, current='{task.status}'")

            task.status = QUEUE_STATUS_PAUSED
            self._touch(task)
            self._save()
            return task.to_dict()

    def resume_task(self, queue_task_id: str) -> Dict[str, Any]:
        with self._lock:
            task = self._get_task_or_raise(queue_task_id)
            if task.status != QUEUE_STATUS_PAUSED:
                raise ValueError(f"only paused task can be resumed, current='{task.status}'")

            # 重新丟回 pending，由 scheduler 重新撿起來
            task.status = QUEUE_STATUS_PENDING
            self._touch(task)
            self._save()
            return task.to_dict()

    def cancel_task(self, queue_task_id: str) -> Dict[str, Any]:
        with self._lock:
            task = self._get_task_or_raise(queue_task_id)
            if task.status in {
                QUEUE_STATUS_FINISHED,
                QUEUE_STATUS_FAILED,
                QUEUE_STATUS_CANCELLED,
            }:
                raise ValueError(f"cannot cancel task from status '{task.status}'")

            task.status = QUEUE_STATUS_CANCELLED
            task.finished_at = utc_now_iso()
            self._touch(task)
            self._save()
            return task.to_dict()

    def reprioritize(self, queue_task_id: str, priority: int) -> Dict[str, Any]:
        with self._lock:
            task = self._get_task_or_raise(queue_task_id)
            task.priority = int(priority)
            self._touch(task)
            self._save()
            return task.to_dict()

    def remove_terminal_task(self, queue_task_id: str) -> Dict[str, Any]:
        with self._lock:
            idx = self._find_index(queue_task_id)
            if idx < 0:
                raise ValueError(f"queue task not found: {queue_task_id}")

            task = self._tasks[idx]
            if task.status not in {
                QUEUE_STATUS_FINISHED,
                QUEUE_STATUS_FAILED,
                QUEUE_STATUS_CANCELLED,
            }:
                raise ValueError(
                    f"only terminal task can be removed, current='{task.status}'"
                )

            removed = self._tasks.pop(idx)
            self._save()
            return removed.to_dict()

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            counts = {
                QUEUE_STATUS_PENDING: 0,
                QUEUE_STATUS_RUNNING: 0,
                QUEUE_STATUS_PAUSED: 0,
                QUEUE_STATUS_FINISHED: 0,
                QUEUE_STATUS_FAILED: 0,
                QUEUE_STATUS_CANCELLED: 0,
            }

            for task in self._tasks:
                counts[task.status] = counts.get(task.status, 0) + 1

            return {
                "queue_file": str(self.queue_file),
                "total": len(self._tasks),
                "counts": counts,
                "next_runnable": (
                    self.get_next_runnable_task().to_dict()
                    if self.get_next_runnable_task()
                    else None
                ),
            }