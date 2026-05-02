from __future__ import annotations

import copy
from typing import Any, Dict, List

from core.worker.worker_contracts import (
    WorkerTask,
    create_scheduler_queue_item,
    create_scheduler_state,
    ensure_scheduler_state_contract,
    ensure_worker_result_contract,
    ensure_worker_task_contract,
)
from core.worker.worker_runtime import WorkerRuntime


class WorkerScheduler:
    """
    Deterministic single-worker-at-a-time scheduler.

    It keeps a simple queue, runs worker_task items in order, retries failed
    items a fixed number of times, and updates scheduler/worker state. It does
    not plan, split tasks, run in parallel, or route between agents.
    """

    def __init__(self, *, runtime: WorkerRuntime, max_retries: int = 0) -> None:
        self.runtime = runtime
        self.max_retries = max(0, int(max_retries or 0))
        self._queue: List[Dict[str, Any]] = []
        self._done: List[Dict[str, Any]] = []
        self._failed: List[Dict[str, Any]] = []
        self._tick_count = 0
        self._last_event = ""

    def enqueue(self, worker_task: WorkerTask | Dict[str, Any], *, max_retries: int | None = None) -> Dict[str, Any]:
        task_payload = self._coerce_task(worker_task)
        item = create_scheduler_queue_item(
            task=task_payload,
            status="pending",
            attempts=0,
            max_retries=self.max_retries if max_retries is None else max(0, int(max_retries or 0)),
            last_result={},
        ).to_dict()
        self._queue.append(copy.deepcopy(item))
        self._last_event = f"enqueued:{task_payload['task_id']}"
        return copy.deepcopy(item)

    def run_next(self) -> Dict[str, Any]:
        self._tick_count += 1
        index = self._next_pending_index()
        if index is None:
            self._last_event = "idle"
            return {
                "ok": True,
                "event": "idle",
                "state": self.snapshot_state(),
                "worker_result": {},
            }

        item = self._queue[index]
        item["status"] = "running"
        item["attempts"] = int(item.get("attempts") or 0) + 1
        task = copy.deepcopy(item["task"])
        self._last_event = f"running:{task['task_id']}"

        runner_result = self.runtime.run_task(task)
        worker_result = self.runtime.collect_result(task, runner_result)
        ensure_worker_result_contract(worker_result)
        item["last_result"] = copy.deepcopy(worker_result)

        if worker_result["status"] in {"success", "partial"}:
            item["status"] = "done"
            self._queue.pop(index)
            self.runtime.merge_result(worker_result)
            self._done.append(copy.deepcopy(item))
            self._last_event = f"done:{task['task_id']}"
            return {
                "ok": True,
                "event": "done",
                "task_id": task["task_id"],
                "worker_result": worker_result,
                "state": self.snapshot_state(),
                "worker_state": self.runtime.snapshot_state(),
            }

        if item["attempts"] <= item["max_retries"]:
            item["status"] = "pending"
            self._queue[index] = copy.deepcopy(item)
            self._last_event = f"retry:{task['task_id']}"
            return {
                "ok": False,
                "event": "retry",
                "task_id": task["task_id"],
                "worker_result": worker_result,
                "state": self.snapshot_state(),
                "worker_state": self.runtime.snapshot_state(),
            }

        item["status"] = "failed"
        self._queue.pop(index)
        self.runtime.merge_result(worker_result)
        self._failed.append(copy.deepcopy(item))
        self._last_event = f"failed:{task['task_id']}"
        return {
            "ok": False,
            "event": "failed",
            "task_id": task["task_id"],
            "worker_result": worker_result,
            "state": self.snapshot_state(),
            "worker_state": self.runtime.snapshot_state(),
        }

    def run_until_idle(self, *, max_ticks: int = 100) -> Dict[str, Any]:
        events = []
        limit = max(1, int(max_ticks or 1))
        for _ in range(limit):
            if self._next_pending_index() is None:
                break
            event = self.run_next()
            events.append(copy.deepcopy(event))

        return {
            "ok": not self._failed,
            "events": events,
            "state": self.snapshot_state(),
            "worker_state": self.runtime.snapshot_state(),
        }

    def snapshot_state(self) -> Dict[str, Any]:
        state = create_scheduler_state(
            queue=self._queue,
            done=self._done,
            failed=self._failed,
            tick_count=self._tick_count,
            last_event=self._last_event,
        ).to_dict()
        ensure_scheduler_state_contract(state)
        return state

    def _next_pending_index(self) -> int | None:
        for index, item in enumerate(self._queue):
            if item.get("status") == "pending":
                return index
        return None

    def _coerce_task(self, worker_task: WorkerTask | Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(worker_task, WorkerTask):
            payload = worker_task.to_dict()
        else:
            payload = copy.deepcopy(worker_task)
        return ensure_worker_task_contract(payload)
