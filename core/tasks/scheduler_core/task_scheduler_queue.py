from __future__ import annotations

import heapq
import itertools
import copy
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from core.runtime.runtime_authority_seal import is_task_completion_authority
from core.runtime.persistent_queue_contract import (
    QUEUE_LINEAGE_FIELDS,
    duplicate_identity,
    extract_queue_lineage,
    merge_queue_lineage,
    queue_identity,
    queue_session_id,
)


STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_FINISHED = "finished"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"


@dataclass
class ScheduledTask:
    task_id: str
    title: str = ""
    priority: int = 0
    created_at: float = field(default_factory=time.time)
    status: str = STATUS_QUEUED
    retry_count: int = 0
    max_retries: int = 0
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    last_error: Optional[str] = None
    result: Any = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "priority": self.priority,
            "created_at": self.created_at,
            "status": self.status,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "payload": self.payload,
            "metadata": self.metadata,
            "last_error": self.last_error,
            "result": self.result,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class TaskSchedulerQueue:
    """
    任務排程佇列：
    - 管 queued tasks
    - 管 priority queue
    - 不負責真正執行
    - 不負責 worker slot
    - 不負責 executor 細節

    排序規則：
    1. priority 越大越先跑
    2. created_at 越早越先跑
    3. sequence 越早越先跑（避免同時間衝突）

    重要：
    - Queue 不應該決定 DAG / repo 的邏輯狀態
    - enqueue() 不再強制覆蓋 status = queued
    - 只有 scheduler 應該決定 blocked / queued
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._heap: List[Tuple[int, float, int, str]] = []
        self._sequence = itertools.count()

        self._tasks: Dict[str, ScheduledTask] = {}
        self._queued_ids: set[str] = set()
        self.last_admission_result: Dict[str, Any] = {}

    def __len__(self) -> int:
        with self._lock:
            return len(self._queued_ids)

    def size(self) -> int:
        with self._lock:
            return len(self._queued_ids)

    def is_empty(self) -> bool:
        with self._lock:
            return len(self._queued_ids) == 0

    def has_task(self, task_id: str) -> bool:
        with self._lock:
            return self._resolve_key(task_id) is not None

    def contains(self, task_id: str) -> bool:
        with self._lock:
            key = self._resolve_key(task_id)
            return key in self._queued_ids if key is not None else False

    def get_task(
        self,
        task_id: str,
        *,
        session_id: str | None = None,
        goal_lineage_id: str | None = None,
        branch_id: str | None = None,
    ) -> Optional[ScheduledTask]:
        with self._lock:
            key = self._resolve_key(
                task_id,
                session_id=session_id,
                goal_lineage_id=goal_lineage_id,
                branch_id=branch_id,
            )
            task = self._tasks.get(key) if key is not None else None
            return None if task is None else self._clone_task(task)

    def upsert_task(self, task: ScheduledTask) -> ScheduledTask:
        with self._lock:
            key = self._storage_key(task)
            existing = self._tasks.get(key)
            if existing is None:
                self._tasks[key] = self._clone_task(task)
            else:
                existing.title = task.title
                existing.priority = task.priority
                existing.payload = dict(task.payload)
                existing.metadata = dict(task.metadata)
                existing.max_retries = task.max_retries
                existing.status = task.status
                existing.retry_count = task.retry_count
                existing.last_error = task.last_error
                existing.result = task.result
                existing.started_at = task.started_at
                existing.finished_at = task.finished_at
            return self._clone_task(self._tasks[key])

    def enqueue(self, task: ScheduledTask, overwrite: bool = False) -> bool:
        with self._lock:
            storage_key = self._storage_key(task)
            existing = self._tasks.get(storage_key)

            semantic_duplicate, matched_identity = duplicate_identity(
                task.payload,
                [item.payload for key, item in self._tasks.items() if key != storage_key],
            )
            if semantic_duplicate is not None:
                self.last_admission_result = {
                    "result": "duplicate_idempotent",
                    "task_id": task.task_id,
                    "matched_identity": matched_identity,
                }
                return False

            if existing is not None:
                if storage_key in self._queued_ids:
                    if not overwrite:
                        self.last_admission_result = {
                            "result": "duplicate_idempotent",
                            "task_id": task.task_id,
                            "matched_identity": queue_identity(existing.payload) or {"task_id": task.task_id},
                        }
                        return False
                    self._remove_from_queue_marker(storage_key)

                if not overwrite:
                    self.last_admission_result = {
                        "result": "duplicate_idempotent",
                        "task_id": task.task_id,
                        "matched_identity": queue_identity(existing.payload) or {"task_id": task.task_id},
                    }
                    return False

            stored = self._clone_task(task)
            lineage_conflicts: List[Dict[str, Any]] = []
            if existing is not None:
                sealed_payload, lineage_conflicts = merge_queue_lineage(
                    existing.payload, task.payload, preserve_existing_evidence=True
                )
                for key, value in task.payload.items():
                    if key not in QUEUE_LINEAGE_FIELDS:
                        sealed_payload[key] = copy.deepcopy(value)
                stored.payload = sealed_payload

            # 關鍵修正：
            # 不要在 queue 層強制覆蓋 status = queued
            # 這個狀態應由 scheduler / repo 決定
            #
            # 原本有這行，會把 blocked 任務也洗成 queued：
            # stored.status = STATUS_QUEUED

            stored.started_at = None
            stored.finished_at = None
            stored.result = None
            stored.last_error = None

            self._tasks[storage_key] = stored

            seq = next(self._sequence)
            heapq.heappush(
                self._heap,
                (-stored.priority, stored.created_at, seq, storage_key),
            )
            self._queued_ids.add(storage_key)
            self.last_admission_result = {
                "result": "requeued" if existing is not None else "enqueued",
                "task_id": stored.task_id,
                "identity": queue_identity(stored.payload),
                "lineage_conflicts": lineage_conflicts,
            }
            return True

    def enqueue_from_dict(self, data: Dict[str, Any], overwrite: bool = False) -> bool:
        task = ScheduledTask(
            task_id=str(data["task_id"]),
            title=str(data.get("title", "")),
            priority=int(data.get("priority", 0)),
            created_at=float(data.get("created_at", time.time())),
            status=str(data.get("status", STATUS_QUEUED)),
            retry_count=int(data.get("retry_count", 0)),
            max_retries=int(data.get("max_retries", 0)),
            payload=dict(data.get("payload", {})),
            metadata=dict(data.get("metadata", {})),
            last_error=data.get("last_error"),
            result=data.get("result"),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
        )
        return self.enqueue(task, overwrite=overwrite)

    def extend(self, tasks: List[ScheduledTask], overwrite: bool = False) -> int:
        added = 0
        for task in tasks:
            if self.enqueue(task, overwrite=overwrite):
                added += 1
        return added

    def pop_next(self) -> Optional[ScheduledTask]:
        with self._lock:
            while self._heap:
                _, _, _, task_id = heapq.heappop(self._heap)
                if task_id not in self._queued_ids:
                    continue

                self._queued_ids.remove(task_id)
                task = self._tasks.get(task_id)
                if task is None:
                    continue

                task.status = STATUS_RUNNING
                task.started_at = time.time()
                return self._clone_task(task)

            return None

    def dequeue(self) -> Optional[ScheduledTask]:
        return self.pop_next()

    def peek_next(self) -> Optional[ScheduledTask]:
        with self._lock:
            while self._heap:
                _, _, _, task_id = self._heap[0]
                if task_id not in self._queued_ids:
                    heapq.heappop(self._heap)
                    continue

                task = self._tasks.get(task_id)
                if task is None:
                    heapq.heappop(self._heap)
                    self._queued_ids.discard(task_id)
                    continue

                return self._clone_task(task)

            return None

    def requeue(
        self,
        task_id: str,
        priority: Optional[int] = None,
        error: Optional[str] = None,
        *,
        session_id: str | None = None,
    ) -> bool:
        with self._lock:
            key = self._resolve_key(task_id, session_id=session_id)
            task = self._tasks.get(key) if key is not None else None
            if task is None:
                return False

            if key in self._queued_ids:
                return False

            task.status = STATUS_QUEUED
            task.started_at = None
            task.finished_at = None
            task.result = None
            if error is not None:
                task.last_error = error
            if priority is not None:
                task.priority = int(priority)

            seq = next(self._sequence)
            heapq.heappush(
                self._heap,
                (-task.priority, task.created_at, seq, key),
            )
            self._queued_ids.add(key)
            return True

    def cancel(self, task_id: str, *, session_id: str | None = None) -> bool:
        with self._lock:
            key = self._resolve_key(task_id, session_id=session_id)
            task = self._tasks.get(key) if key is not None else None
            if task is None:
                return False

            self._queued_ids.discard(key)
            task.status = STATUS_CANCELLED
            task.finished_at = time.time()
            return True

    def mark_finished(self, task_id: str, result: Any = None, *, completion_authority: Any = None, session_id: str | None = None) -> bool:
        with self._lock:
            key = self._resolve_key(task_id, session_id=session_id)
            task = self._tasks.get(key) if key is not None else None
            if task is None:
                return False
            task_session_id = queue_session_id(task.payload) or queue_session_id(task.metadata)
            if not is_task_completion_authority(
                completion_authority,
                task_id=task_id,
                session_id=task_session_id or None,
            ):
                raise PermissionError("task_completion_authority_required")

            self._queued_ids.discard(key)
            task.status = STATUS_FINISHED
            task.result = result
            task.finished_at = time.time()
            return True

    def mark_failed(self, task_id: str, error: str, *, session_id: str | None = None) -> bool:
        with self._lock:
            key = self._resolve_key(task_id, session_id=session_id)
            task = self._tasks.get(key) if key is not None else None
            if task is None:
                return False

            self._queued_ids.discard(key)
            task.status = STATUS_FAILED
            task.last_error = error
            task.finished_at = time.time()
            return True

    def increment_retry(self, task_id: str, *, session_id: str | None = None) -> bool:
        with self._lock:
            key = self._resolve_key(task_id, session_id=session_id)
            task = self._tasks.get(key) if key is not None else None
            if task is None:
                return False
            task.retry_count += 1
            return True

    def update_priority(self, task_id: str, priority: int, *, session_id: str | None = None) -> bool:
        with self._lock:
            key = self._resolve_key(task_id, session_id=session_id)
            task = self._tasks.get(key) if key is not None else None
            if task is None:
                return False

            task.priority = int(priority)

            if key in self._queued_ids:
                seq = next(self._sequence)
                heapq.heappush(
                    self._heap,
                    (-task.priority, task.created_at, seq, key),
                )
            return True

    def remove(self, task_id: str, *, session_id: str | None = None) -> bool:
        with self._lock:
            key = self._resolve_key(task_id, session_id=session_id)
            existed = key in self._tasks if key is not None else False
            if key is not None:
                self._queued_ids.discard(key)
                self._tasks.pop(key, None)
            return existed

    def list_queued(self) -> List[ScheduledTask]:
        with self._lock:
            items: List[ScheduledTask] = []
            seen: set[str] = set()

            snapshot = list(self._heap)
            snapshot.sort()

            for _, _, _, task_id in snapshot:
                if task_id in seen:
                    continue
                if task_id not in self._queued_ids:
                    continue

                task = self._tasks.get(task_id)
                if task is None:
                    continue

                items.append(self._clone_task(task))
                seen.add(task_id)

            return items

    def list_all(self) -> List[ScheduledTask]:
        with self._lock:
            tasks = [self._clone_task(task) for task in self._tasks.values()]
            tasks.sort(
                key=lambda x: (
                    self._status_rank(x.status),
                    -x.priority,
                    x.created_at,
                    x.task_id,
                )
            )
            return tasks

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            status_counts: Dict[str, int] = {}
            for task in self._tasks.values():
                status_counts[task.status] = status_counts.get(task.status, 0) + 1

            next_task = self.peek_next()
            return {
                "queued_count": len(self._queued_ids),
                "total_count": len(self._tasks),
                "status_counts": status_counts,
                "next_task": None if next_task is None else next_task.to_dict(),
            }

    def _remove_from_queue_marker(self, task_id: str) -> None:
        self._queued_ids.discard(task_id)

    @staticmethod
    def _storage_key(task: ScheduledTask) -> str:
        session_id = queue_session_id(task.payload) or queue_session_id(task.metadata)
        lineage = extract_queue_lineage(task.payload)
        lineage_id = str(lineage.get("goal_lineage_id") or "").strip()
        branch_id = str(lineage.get("branch_id") or "").strip()
        if lineage_id and branch_id:
            return "::".join((session_id, lineage_id, branch_id, task.task_id))
        return f"{session_id}::{task.task_id}" if session_id else task.task_id

    def _resolve_key(
        self,
        task_id: str,
        *,
        session_id: str | None = None,
        goal_lineage_id: str | None = None,
        branch_id: str | None = None,
    ) -> str | None:
        clean_task_id = str(task_id or "").strip()
        clean_session_id = str(session_id or "").strip()
        if clean_session_id:
            key = f"{clean_session_id}::{clean_task_id}"
            if key in self._tasks and not goal_lineage_id and not branch_id:
                return key
        if clean_task_id in self._tasks:
            return clean_task_id
        matches = []
        for key, task in self._tasks.items():
            lineage = extract_queue_lineage(task.payload)
            if task.task_id != clean_task_id:
                continue
            if clean_session_id and queue_session_id(task.payload) != clean_session_id:
                continue
            if goal_lineage_id and lineage.get("goal_lineage_id") != str(goal_lineage_id):
                continue
            if branch_id and lineage.get("branch_id") != str(branch_id):
                continue
            matches.append(key)
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _clone_task(task: ScheduledTask) -> ScheduledTask:
        return ScheduledTask(
            task_id=task.task_id,
            title=task.title,
            priority=task.priority,
            created_at=task.created_at,
            status=task.status,
            retry_count=task.retry_count,
            max_retries=task.max_retries,
            payload=dict(task.payload),
            metadata=dict(task.metadata),
            last_error=task.last_error,
            result=task.result,
            started_at=task.started_at,
            finished_at=task.finished_at,
        )

    @staticmethod
    def _status_rank(status: str) -> int:
        ranking = {
            STATUS_RUNNING: 0,
            STATUS_QUEUED: 1,
            STATUS_FAILED: 2,
            STATUS_FINISHED: 3,
            STATUS_CANCELLED: 4,
        }
        return ranking.get(status, 99)
