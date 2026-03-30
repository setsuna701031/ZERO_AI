# core/tasks/task_queue.py
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_FINISHED = "finished"
STATUS_FAILED = "failed"
STATUS_RETRYING = "retrying"
STATUS_WAITING = "waiting"
STATUS_BLOCKED = "blocked"
STATUS_PAUSED = "paused"
STATUS_CANCELED = "canceled"


class TaskQueue:
    """
    給目前 ZERO Task OS 使用的最小可運作 TaskQueue

    提供：
    - enqueue(...)
    - dequeue()
    - requeue(task)
    - list_tasks()
    - get_task(task_name)
    - pause_task(task_name)
    - resume_task(task_name)
    - cancel_task(task_name)
    - set_task_priority(task_name, priority)
    - get_scheduler_state()
    - reset_scheduler_state()
    - has_tasks()
    """

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root = os.path.abspath(workspace_root)
        os.makedirs(self.workspace_root, exist_ok=True)

        self.tasks_file = os.path.join(self.workspace_root, "tasks.json")
        self.scheduler_state_file = os.path.join(self.workspace_root, "scheduler_state.json")

        self._ensure_files()

    # =========================================================
    # File helpers
    # =========================================================

    def _ensure_files(self) -> None:
        if not os.path.exists(self.tasks_file):
            self._save_tasks([])

        if not os.path.exists(self.scheduler_state_file):
            self._save_scheduler_state(
                {
                    "current_task_name": None,
                    "queued_task_names": [],
                    "paused_task_names": [],
                    "waiting_task_names": [],
                    "retrying_task_names": [],
                    "blocked_task_names": [],
                    "queued_count": 0,
                    "paused_count": 0,
                    "waiting_count": 0,
                    "retrying_count": 0,
                    "blocked_count": 0,
                    "tick": 0,
                    "has_work": False,
                }
            )

    def _load_tasks(self) -> List[Dict[str, Any]]:
        self._ensure_files()
        try:
            with open(self.tasks_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = []

        if not isinstance(data, list):
            return []

        result: List[Dict[str, Any]] = []
        for item in data:
            if isinstance(item, dict):
                try:
                    result.append(self._normalize_task(item))
                except Exception:
                    continue
        return result

    def _save_tasks(self, tasks: List[Dict[str, Any]]) -> None:
        normalized = [self._normalize_task(t) for t in tasks]
        with open(self.tasks_file, "w", encoding="utf-8") as f:
            json.dump(normalized, f, ensure_ascii=False, indent=2)

    def _load_scheduler_state(self) -> Dict[str, Any]:
        self._ensure_files()
        try:
            with open(self.scheduler_state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

        if not isinstance(data, dict):
            data = {}

        return {
            "current_task_name": data.get("current_task_name"),
            "queued_task_names": list(data.get("queued_task_names", [])),
            "paused_task_names": list(data.get("paused_task_names", [])),
            "waiting_task_names": list(data.get("waiting_task_names", [])),
            "retrying_task_names": list(data.get("retrying_task_names", [])),
            "blocked_task_names": list(data.get("blocked_task_names", [])),
            "queued_count": int(data.get("queued_count", 0)),
            "paused_count": int(data.get("paused_count", 0)),
            "waiting_count": int(data.get("waiting_count", 0)),
            "retrying_count": int(data.get("retrying_count", 0)),
            "blocked_count": int(data.get("blocked_count", 0)),
            "tick": int(data.get("tick", 0)),
            "has_work": bool(data.get("has_work", False)),
        }

    def _save_scheduler_state(self, state: Dict[str, Any]) -> None:
        with open(self.scheduler_state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    # =========================================================
    # Task helpers
    # =========================================================

    def _normalize_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_id = str(task.get("id") or task.get("task_name") or "").strip()
        if not task_id:
            raise ValueError("task id missing")

        workspace = str(task.get("workspace") or os.path.join(self.workspace_root, task_id))
        os.makedirs(workspace, exist_ok=True)

        history = task.get("history", ["queued"])
        if not isinstance(history, list):
            history = ["queued"]
        if not history:
            history = ["queued"]

        return {
            "id": task_id,
            "task_name": task_id,
            "goal": str(task.get("goal", "")),
            "workspace": workspace,
            "status": str(task.get("status", STATUS_QUEUED)),
            "priority": int(task.get("priority", 0)),
            "retry_count": int(task.get("retry_count", 0)),
            "max_retries": int(task.get("max_retries", 0)),
            "retry_delay": int(task.get("retry_delay", 0)),
            "timeout_ticks": int(task.get("timeout_ticks", 0)),
            "depends_on": list(task.get("depends_on", []) or []),
            "simulate": str(task.get("simulate", "")),
            "required_ticks": int(task.get("required_ticks", 1)),
            "history": history,
        }

    def _append_history(self, task: Dict[str, Any], new_status: str) -> None:
        old_status = str(task.get("status", ""))
        if old_status != new_status:
            task.setdefault("history", [])
            task["history"].append(f"{old_status} -> {new_status}")
        task["status"] = new_status

    def _allocate_task_id(self, tasks: List[Dict[str, Any]]) -> str:
        nums: List[int] = []
        for task in tasks:
            task_id = str(task.get("id", ""))
            if task_id.startswith("task_"):
                tail = task_id[5:]
                if tail.isdigit():
                    nums.append(int(tail))
        next_num = max(nums) + 1 if nums else 1
        return f"task_{next_num:04d}"

    def _replace_task(self, updated_task: Dict[str, Any]) -> Dict[str, Any]:
        tasks = self._load_tasks()
        replaced = False

        for i, task in enumerate(tasks):
            if task.get("id") == updated_task.get("id"):
                tasks[i] = self._normalize_task(updated_task)
                replaced = True
                break

        if not replaced:
            tasks.append(self._normalize_task(updated_task))

        self._save_tasks(tasks)
        self._refresh_scheduler_state()
        return self._normalize_task(updated_task)

    # =========================================================
    # Public API
    # =========================================================

    def enqueue(
        self,
        *,
        goal: str,
        priority: int = 0,
        max_retries: int = 0,
        retry_delay: int = 0,
        timeout_ticks: int = 0,
        depends_on: Optional[List[str]] = None,
        simulate: str = "",
        required_ticks: int = 1,
    ) -> Dict[str, Any]:
        tasks = self._load_tasks()
        task_id = self._allocate_task_id(tasks)
        workspace = os.path.join(self.workspace_root, task_id)
        os.makedirs(workspace, exist_ok=True)

        task = self._normalize_task(
            {
                "id": task_id,
                "goal": goal,
                "workspace": workspace,
                "status": STATUS_QUEUED,
                "priority": priority,
                "retry_count": 0,
                "max_retries": max_retries,
                "retry_delay": retry_delay,
                "timeout_ticks": timeout_ticks,
                "depends_on": depends_on or [],
                "simulate": simulate,
                "required_ticks": required_ticks,
                "history": ["queued"],
            }
        )

        tasks.append(task)
        self._save_tasks(tasks)
        self._refresh_scheduler_state()
        return task

    def dequeue(self) -> Optional[Dict[str, Any]]:
        tasks = self._load_tasks()

        queued_tasks = [t for t in tasks if str(t.get("status", "")).lower() == STATUS_QUEUED]
        if not queued_tasks:
            self._refresh_scheduler_state()
            return None

        queued_tasks.sort(key=lambda t: (-int(t.get("priority", 0)), str(t.get("id", ""))))
        selected = queued_tasks[0]

        for task in tasks:
            if task["id"] == selected["id"]:
                self._append_history(task, STATUS_RUNNING)
                selected = task
                break

        self._save_tasks(tasks)
        self._refresh_scheduler_state(current_task_name=selected["id"])
        return selected

    def requeue(self, task: Dict[str, Any]) -> Dict[str, Any]:
        tasks = self._load_tasks()

        for item in tasks:
            if item["id"] == task["id"]:
                self._append_history(item, STATUS_QUEUED)
                updated = item
                break
        else:
            updated = self._normalize_task(task)
            self._append_history(updated, STATUS_QUEUED)
            tasks.append(updated)

        self._save_tasks(tasks)
        self._refresh_scheduler_state()
        return updated

    def get_task(self, task_name: str) -> Optional[Dict[str, Any]]:
        tasks = self._load_tasks()
        for task in tasks:
            if task.get("id") == task_name or task.get("task_name") == task_name:
                return task
        return None

    def list_tasks(self) -> List[Dict[str, Any]]:
        return self._load_tasks()

    def pause_task(self, task_name: str) -> Dict[str, Any]:
        task = self.get_task(task_name)
        if task is None:
            raise ValueError(f"Task not found: {task_name}")
        self._append_history(task, STATUS_PAUSED)
        return self._replace_task(task)

    def resume_task(self, task_name: str) -> Dict[str, Any]:
        task = self.get_task(task_name)
        if task is None:
            raise ValueError(f"Task not found: {task_name}")
        self._append_history(task, STATUS_QUEUED)
        return self._replace_task(task)

    def cancel_task(self, task_name: str) -> Dict[str, Any]:
        task = self.get_task(task_name)
        if task is None:
            raise ValueError(f"Task not found: {task_name}")
        self._append_history(task, STATUS_CANCELED)
        return self._replace_task(task)

    def set_task_priority(self, task_name: str, priority: int) -> Dict[str, Any]:
        task = self.get_task(task_name)
        if task is None:
            raise ValueError(f"Task not found: {task_name}")
        task["priority"] = int(priority)
        return self._replace_task(task)

    def has_tasks(self) -> bool:
        tasks = self._load_tasks()
        for task in tasks:
            status = str(task.get("status", "")).lower()
            if status not in {STATUS_FINISHED, STATUS_FAILED, STATUS_CANCELED}:
                return True
        return False

    # =========================================================
    # Scheduler state
    # =========================================================

    def _refresh_scheduler_state(self, current_task_name: Optional[str] = None) -> Dict[str, Any]:
        tasks = self._load_tasks()
        old_state = self._load_scheduler_state()

        queued = []
        paused = []
        waiting = []
        retrying = []
        blocked = []

        for task in tasks:
            task_id = task.get("id", "")
            status = str(task.get("status", "")).lower()

            if status == STATUS_QUEUED:
                queued.append(task_id)
            elif status == STATUS_PAUSED:
                paused.append(task_id)
            elif status == STATUS_WAITING:
                waiting.append(task_id)
            elif status == STATUS_RETRYING:
                retrying.append(task_id)
            elif status == STATUS_BLOCKED:
                blocked.append(task_id)

        state = {
            "current_task_name": current_task_name,
            "queued_task_names": queued,
            "paused_task_names": paused,
            "waiting_task_names": waiting,
            "retrying_task_names": retrying,
            "blocked_task_names": blocked,
            "queued_count": len(queued),
            "paused_count": len(paused),
            "waiting_count": len(waiting),
            "retrying_count": len(retrying),
            "blocked_count": len(blocked),
            "tick": int(old_state.get("tick", 0)),
            "has_work": bool(queued or paused or waiting or retrying or blocked),
        }

        self._save_scheduler_state(state)
        return state

    def get_scheduler_state(self) -> Dict[str, Any]:
        return self._refresh_scheduler_state()

    def reset_scheduler_state(self) -> Dict[str, Any]:
        state = {
            "current_task_name": None,
            "queued_task_names": [],
            "paused_task_names": [],
            "waiting_task_names": [],
            "retrying_task_names": [],
            "blocked_task_names": [],
            "queued_count": 0,
            "paused_count": 0,
            "waiting_count": 0,
            "retrying_count": 0,
            "blocked_count": 0,
            "tick": 0,
            "has_work": self.has_tasks(),
        }
        self._save_scheduler_state(state)
        return state

    def advance_tick(self) -> Dict[str, Any]:
        state = self._load_scheduler_state()
        state["tick"] = int(state.get("tick", 0)) + 1
        self._save_scheduler_state(state)
        return state