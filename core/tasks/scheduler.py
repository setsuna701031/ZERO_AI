from __future__ import annotations

import json
import threading
import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskScheduler:
    """
    ZERO Task Scheduler

    負責：
    - queue 任務入列
    - 背景 worker loop 撿 pending 任務
    - 呼叫 task_launcher(goal, queue_task)
    - 更新任務狀態 running / finished / failed / paused / cancelled
    - 提供 health / list / get / reprioritize / pause / resume / cancel

    設計重點：
    - 單檔 JSON queue，不依賴額外 storage 類，避免你現在整合時再分裂
    - start() 真的會開 worker thread
    - scheduler 啟動後，pending 任務會自動執行
    """

    def __init__(
        self,
        workspace_root: str | Path,
        task_launcher: Callable[[str, Dict[str, Any]], Dict[str, Any]],
        poll_interval: float = 0.5,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.system_dir = self.workspace_root / "_system"
        self.system_dir.mkdir(parents=True, exist_ok=True)

        self.queue_file = self.system_dir / "task_queue.json"
        self.task_launcher = task_launcher
        self.poll_interval = max(float(poll_interval), 0.1)

        self.running = False
        self.last_error = ""
        self.worker_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        # 保留 queue 屬性，讓外部 self.queue = self.scheduler.queue 不會炸
        self.queue = self

        self._ensure_queue_file()

    # =========================================================
    # Lifecycle
    # =========================================================

    def start(self) -> Dict[str, Any]:
        with self._lock:
            if self.running:
                return {
                    "success": True,
                    "message": "scheduler already running",
                }

            self.running = True
            self.last_error = ""
            self.worker_thread = threading.Thread(
                target=self._worker_loop,
                name="ZERO-TaskScheduler-Worker",
                daemon=True,
            )
            self.worker_thread.start()

            return {
                "success": True,
                "message": "scheduler started",
            }

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            self.running = False

        thread = self.worker_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

        return {
            "success": True,
            "message": "scheduler stopped",
        }

    def health(self) -> Dict[str, Any]:
        tasks = self._load_tasks()
        stats = self._build_stats(tasks)

        return {
            "running": self.running,
            "last_error": self.last_error,
            "queue_stats": stats,
        }

    # =========================================================
    # Queue Actions
    # =========================================================

    def enqueue(
        self,
        goal: str,
        priority: int = 100,
        source_task_name: str = "",
        run_mode: str = "normal",
        task_type: str = "general",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        goal = str(goal or "").strip()
        if not goal:
            return {
                "success": False,
                "message": "goal is required",
            }

        now = _utc_now_iso()
        queue_task = {
            "queue_task_id": self._new_queue_task_id(),
            "goal": goal,
            "source_task_name": str(source_task_name or "").strip(),
            "priority": int(priority),
            "status": "pending",
            "created_at": now,
            "updated_at": now,
            "started_at": "",
            "finished_at": "",
            "run_mode": str(run_mode or "normal").strip() or "normal",
            "task_type": str(task_type or "general").strip() or "general",
            "assigned_task_name": "",
            "error": "",
            "metadata": metadata or {},
        }

        with self._lock:
            tasks = self._load_tasks_unlocked()
            tasks.append(queue_task)
            self._save_tasks_unlocked(tasks)

        return {
            "success": True,
            "message": "queue task created",
            "queue_task": deepcopy(queue_task),
        }

    def list_tasks(
        self,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        tasks = self._load_tasks()

        if status:
            clean_status = str(status).strip().lower()
            tasks = [task for task in tasks if str(task.get("status", "")).lower() == clean_status]

        # 新的放後面比較符合你現在的觀察方式；這裡先保持建立順序
        if limit is not None:
            tasks = tasks[-int(limit):]

        return {
            "success": True,
            "tasks": tasks,
            "stats": self._build_stats(self._load_tasks()),
        }

    def get_task(self, queue_task_id: str) -> Dict[str, Any]:
        queue_task_id = str(queue_task_id or "").strip()
        if not queue_task_id:
            return {
                "success": False,
                "message": "queue_task_id is required",
            }

        tasks = self._load_tasks()
        for task in tasks:
            if task.get("queue_task_id") == queue_task_id:
                return {
                    "success": True,
                    "task": deepcopy(task),
                }

        return {
            "success": False,
            "message": f"queue task not found: {queue_task_id}",
        }

    def pause_task(self, queue_task_id: str) -> Dict[str, Any]:
        return self._change_status(
            queue_task_id=queue_task_id,
            allowed_current={"pending"},
            new_status="paused",
        )

    def resume_task(self, queue_task_id: str) -> Dict[str, Any]:
        return self._change_status(
            queue_task_id=queue_task_id,
            allowed_current={"paused"},
            new_status="pending",
        )

    def cancel_task(self, queue_task_id: str) -> Dict[str, Any]:
        return self._change_status(
            queue_task_id=queue_task_id,
            allowed_current={"pending", "paused"},
            new_status="cancelled",
            mark_finished=True,
        )

    def reprioritize(self, queue_task_id: str, priority: int) -> Dict[str, Any]:
        queue_task_id = str(queue_task_id or "").strip()
        if not queue_task_id:
            return {
                "success": False,
                "message": "queue_task_id is required",
            }

        with self._lock:
            tasks = self._load_tasks_unlocked()
            for task in tasks:
                if task.get("queue_task_id") == queue_task_id:
                    if str(task.get("status", "")).lower() not in {"pending", "paused"}:
                        return {
                            "success": False,
                            "message": f"cannot reprioritize task in status={task.get('status', '')}",
                        }

                    task["priority"] = int(priority)
                    task["updated_at"] = _utc_now_iso()
                    self._save_tasks_unlocked(tasks)

                    return {
                        "success": True,
                        "message": "queue task reprioritized",
                        "task": deepcopy(task),
                    }

        return {
            "success": False,
            "message": f"queue task not found: {queue_task_id}",
        }

    # =========================================================
    # Worker Loop
    # =========================================================

    def _worker_loop(self) -> None:
        while self.running:
            try:
                next_task = self._claim_next_runnable_task()

                if next_task is None:
                    time.sleep(self.poll_interval)
                    continue

                self._run_claimed_task(next_task)

            except Exception as exc:
                self.last_error = str(exc)
                time.sleep(max(self.poll_interval, 0.5))

    def _claim_next_runnable_task(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            tasks = self._load_tasks_unlocked()

            pending_tasks = [
                task
                for task in tasks
                if str(task.get("status", "")).lower() == "pending"
            ]

            if not pending_tasks:
                return None

            # 先按 priority，小的先；再按 created_at，早的先
            pending_tasks.sort(
                key=lambda item: (
                    int(item.get("priority", 100)),
                    str(item.get("created_at", "")),
                )
            )

            selected_id = pending_tasks[0].get("queue_task_id")

            for task in tasks:
                if task.get("queue_task_id") == selected_id:
                    task["status"] = "running"
                    task["started_at"] = _utc_now_iso()
                    task["updated_at"] = task["started_at"]
                    task["error"] = ""
                    self._save_tasks_unlocked(tasks)
                    return deepcopy(task)

        return None

    def _run_claimed_task(self, queue_task: Dict[str, Any]) -> None:
        queue_task_id = str(queue_task.get("queue_task_id", "")).strip()
        goal = str(queue_task.get("goal", "")).strip()

        try:
            result = self.task_launcher(goal, deepcopy(queue_task))
            if not isinstance(result, dict):
                raise RuntimeError("task_launcher must return a dict")

            success = bool(result.get("success", False))
            assigned_task_name = str(result.get("task_name", "")).strip()
            error = str(result.get("error", "") or "").strip()

            if success:
                self._mark_finished(
                    queue_task_id=queue_task_id,
                    assigned_task_name=assigned_task_name,
                )
            else:
                self._mark_failed(
                    queue_task_id=queue_task_id,
                    error=error or "task launcher returned success=False",
                    assigned_task_name=assigned_task_name,
                )

        except Exception as exc:
            self.last_error = str(exc)
            self._mark_failed(
                queue_task_id=queue_task_id,
                error=str(exc),
                assigned_task_name="",
            )

    # =========================================================
    # Status Updates
    # =========================================================

    def _mark_finished(self, queue_task_id: str, assigned_task_name: str = "") -> None:
        with self._lock:
            tasks = self._load_tasks_unlocked()
            for task in tasks:
                if task.get("queue_task_id") == queue_task_id:
                    now = _utc_now_iso()
                    task["status"] = "finished"
                    task["updated_at"] = now
                    task["finished_at"] = now
                    if assigned_task_name:
                        task["assigned_task_name"] = assigned_task_name
                    task["error"] = ""
                    self._save_tasks_unlocked(tasks)
                    return

    def _mark_failed(
        self,
        queue_task_id: str,
        error: str,
        assigned_task_name: str = "",
    ) -> None:
        with self._lock:
            tasks = self._load_tasks_unlocked()
            for task in tasks:
                if task.get("queue_task_id") == queue_task_id:
                    now = _utc_now_iso()
                    task["status"] = "failed"
                    task["updated_at"] = now
                    task["finished_at"] = now
                    if assigned_task_name:
                        task["assigned_task_name"] = assigned_task_name
                    task["error"] = str(error or "").strip()
                    self._save_tasks_unlocked(tasks)
                    return

    def _change_status(
        self,
        queue_task_id: str,
        allowed_current: set[str],
        new_status: str,
        mark_finished: bool = False,
    ) -> Dict[str, Any]:
        queue_task_id = str(queue_task_id or "").strip()
        if not queue_task_id:
            return {
                "success": False,
                "message": "queue_task_id is required",
            }

        with self._lock:
            tasks = self._load_tasks_unlocked()
            for task in tasks:
                if task.get("queue_task_id") != queue_task_id:
                    continue

                current_status = str(task.get("status", "")).lower()
                if current_status not in allowed_current:
                    return {
                        "success": False,
                        "message": f"cannot change status from {task.get('status', '')} to {new_status}",
                    }

                now = _utc_now_iso()
                task["status"] = new_status
                task["updated_at"] = now

                if mark_finished:
                    task["finished_at"] = now

                self._save_tasks_unlocked(tasks)
                return {
                    "success": True,
                    "message": f"queue task {new_status}",
                    "task": deepcopy(task),
                }

        return {
            "success": False,
            "message": f"queue task not found: {queue_task_id}",
        }

    # =========================================================
    # Queue File Helpers
    # =========================================================

    def _ensure_queue_file(self) -> None:
        with self._lock:
            if self.queue_file.exists():
                try:
                    data = json.loads(self.queue_file.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        return
                except Exception:
                    pass

            self.queue_file.write_text("[]", encoding="utf-8")

    def _load_tasks(self) -> List[Dict[str, Any]]:
        with self._lock:
            return self._load_tasks_unlocked()

    def _load_tasks_unlocked(self) -> List[Dict[str, Any]]:
        try:
            if not self.queue_file.exists():
                return []

            raw = self.queue_file.read_text(encoding="utf-8").strip()
            if not raw:
                return []

            data = json.loads(raw)
            if not isinstance(data, list):
                return []

            normalized: List[Dict[str, Any]] = []
            for item in data:
                if isinstance(item, dict):
                    normalized.append(dict(item))
            return normalized
        except Exception:
            return []

    def _save_tasks_unlocked(self, tasks: List[Dict[str, Any]]) -> None:
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        self.queue_file.write_text(
            json.dumps(tasks, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _build_stats(self, tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
        counts = {
            "pending": 0,
            "running": 0,
            "paused": 0,
            "finished": 0,
            "failed": 0,
            "cancelled": 0,
        }

        for task in tasks:
            status = str(task.get("status", "")).strip().lower()
            if status in counts:
                counts[status] += 1

        next_runnable = None
        pending_tasks = [
            task for task in tasks if str(task.get("status", "")).strip().lower() == "pending"
        ]
        if pending_tasks:
            pending_tasks.sort(
                key=lambda item: (
                    int(item.get("priority", 100)),
                    str(item.get("created_at", "")),
                )
            )
            next_runnable = deepcopy(pending_tasks[0])

        return {
            "queue_file": str(self.queue_file),
            "total": len(tasks),
            "counts": counts,
            "next_runnable": next_runnable,
        }

    def _new_queue_task_id(self) -> str:
        return f"qtask_{uuid.uuid4().hex[:12]}"