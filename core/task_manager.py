from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class TaskManager:
    """
    Task Manager
    負責：
    - 任務建立 / 更新
    - 任務狀態
    - pause / resume / cancel
    - 任務持久化
    """

    def __init__(self, workspace_root: str = "workspace") -> None:
        self.workspace_root = Path(workspace_root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)

        self.task_file = self.workspace_root / "tasks.json"
        if not self.task_file.exists():
            self._save_tasks({})

    # =========================================================
    # Task Storage
    # =========================================================

    def _load_tasks(self) -> Dict[str, Any]:
        with open(self.task_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_tasks(self, data: Dict[str, Any]) -> None:
        with open(self.task_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # =========================================================
    # Create / Upsert Task
    # =========================================================

    def create_task(self, task_id: str, title: str) -> None:
        tasks = self._load_tasks()

        tasks[task_id] = {
            "id": task_id,
            "task_id": task_id,
            "task_name": task_id,
            "title": title,
            "goal": title,
            "status": "pending",
            "created_at": time.time(),
            "updated_at": time.time(),
            "priority": 100,
            "dependencies": [],
            "max_retries": 0,
            "retry_delay_ticks": 0,
            "retry_count": 0,
            "next_retry_tick": 0,
            "last_error": None,
        }

        self._save_tasks(tasks)

    def upsert_task(self, task: Dict[str, Any]) -> None:
        if not isinstance(task, dict) or not task:
            return

        task_id = (
            task.get("task_name")
            or task.get("id")
            or task.get("task_id")
        )
        if not task_id:
            return

        tasks = self._load_tasks()
        existing = tasks.get(task_id, {})
        if not isinstance(existing, dict):
            existing = {}

        merged = dict(existing)
        merged.update(task)
        merged["updated_at"] = time.time()

        if "created_at" not in merged:
            merged["created_at"] = time.time()

        tasks[task_id] = merged
        self._save_tasks(tasks)

    # =========================================================
    # Status / Field Update
    # =========================================================

    def update_task_status(self, task_id: str, status: str) -> None:
        tasks = self._load_tasks()
        if task_id not in tasks:
            return

        tasks[task_id]["status"] = status
        tasks[task_id]["updated_at"] = time.time()
        self._save_tasks(tasks)

    def update_task_field(self, task_id: str, field_name: str, value: Any) -> None:
        tasks = self._load_tasks()
        if task_id not in tasks:
            return

        tasks[task_id][field_name] = value
        tasks[task_id]["updated_at"] = time.time()
        self._save_tasks(tasks)

    def update_task(self, task_id: str, updates: Dict[str, Any]) -> None:
        if not isinstance(updates, dict):
            return

        tasks = self._load_tasks()
        if task_id not in tasks:
            return

        tasks[task_id].update(updates)
        tasks[task_id]["updated_at"] = time.time()
        self._save_tasks(tasks)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        tasks = self._load_tasks()
        return tasks.get(task_id)

    def list_tasks(self) -> List[Dict[str, Any]]:
        tasks = self._load_tasks()
        return list(tasks.values())

    # =========================================================
    # Pause / Resume / Cancel
    # =========================================================

    def pause_task(self, task_id: str) -> None:
        tasks = self._load_tasks()
        if task_id in tasks:
            tasks[task_id]["status"] = "paused"
            tasks[task_id]["updated_at"] = time.time()
            self._save_tasks(tasks)

    def resume_task(self, task_id: str) -> None:
        tasks = self._load_tasks()
        if task_id in tasks and tasks[task_id]["status"] == "paused":
            tasks[task_id]["status"] = "queued"
            tasks[task_id]["updated_at"] = time.time()
            self._save_tasks(tasks)

    def cancel_task(self, task_id: str) -> None:
        tasks = self._load_tasks()
        if task_id in tasks:
            tasks[task_id]["status"] = "canceled"
            tasks[task_id]["updated_at"] = time.time()
            self._save_tasks(tasks)

    # =========================================================
    # Legacy helper
    # =========================================================

    def get_next_runnable_task(self) -> Optional[Dict[str, Any]]:
        tasks = self._load_tasks()

        runnable = [
            t for t in tasks.values()
            if str(t.get("status", "")).strip().lower() in {"pending", "queued"}
        ]

        if not runnable:
            return None

        runnable.sort(key=lambda x: x.get("priority", 100))
        return runnable[0]