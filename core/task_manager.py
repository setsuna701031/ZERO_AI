# task_manager.py
from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List, Optional

from task_runtime import (
    TASK_STATUS_BLOCKED,
    TASK_STATUS_CANCELED,
    TASK_STATUS_FAILED,
    TASK_STATUS_FINISHED,
    TASK_STATUS_PAUSED,
    TASK_STATUS_QUEUED,
    TASK_STATUS_RETRYING,
    TASK_STATUS_RUNNING,
    TASK_STATUS_WAITING,
    TaskRuntime,
)


class TaskManager:
    """
    TaskManager 負責：
    - tasks.json 的讀寫
    - task 建立 / 更新 / 查詢
    - queue-list 所需資料整理
    - 與 TaskRuntime 同步欄位

    這版刻意維持保守：
    - 不把 scheduler 邏輯塞進來
    - 不把 step executor 硬綁在這裡
    - 先把 Task OS 的資料層打穩
    """

    def __init__(self, workspace_dir: str = "workspace") -> None:
        self.workspace_dir = os.path.abspath(workspace_dir)
        os.makedirs(self.workspace_dir, exist_ok=True)

        self.tasks_file = os.path.join(self.workspace_dir, "tasks.json")
        self.scheduler_state_file = os.path.join(self.workspace_dir, "scheduler_state.json")

        self.task_runtime = TaskRuntime()
        self._ensure_tasks_file()

    # ------------------------------------------------------------------
    # 基本檔案層
    # ------------------------------------------------------------------

    def _ensure_tasks_file(self) -> None:
        if not os.path.exists(self.tasks_file):
            self._write_tasks([])

    def _read_tasks(self) -> List[Dict[str, Any]]:
        self._ensure_tasks_file()

        try:
            with open(self.tasks_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = []

        if not isinstance(data, list):
            data = []

        normalized: List[Dict[str, Any]] = []
        for task in data:
            try:
                normalized.append(self._normalize_task(task))
            except Exception:
                continue

        return normalized

    def _write_tasks(self, tasks: List[Dict[str, Any]]) -> None:
        os.makedirs(os.path.dirname(self.tasks_file), exist_ok=True)
        with open(self.tasks_file, "w", encoding="utf-8") as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # 對外 API：給 scheduler / app 用
    # ------------------------------------------------------------------

    def get_all_tasks(self) -> List[Dict[str, Any]]:
        tasks = self._read_tasks()
        synced: List[Dict[str, Any]] = []

        for task in tasks:
            self.task_runtime.ensure_runtime_state(task)
            synced_task = self.task_runtime.sync_runtime_fields_back_to_task(task)
            synced.append(self._normalize_task(synced_task))

        self._write_tasks(synced)
        return copy.deepcopy(synced)

    def list_tasks(self) -> List[Dict[str, Any]]:
        return self.get_all_tasks()

    def get_tasks(self) -> List[Dict[str, Any]]:
        return self.get_all_tasks()

    def load_tasks(self) -> List[Dict[str, Any]]:
        return self.get_all_tasks()

    def save_tasks(self, tasks: List[Dict[str, Any]]) -> None:
        normalized = [self._normalize_task(t) for t in tasks]
        self._write_tasks(normalized)

    def set_tasks(self, tasks: List[Dict[str, Any]]) -> None:
        self.save_tasks(tasks)

    def replace_all_tasks(self, tasks: List[Dict[str, Any]]) -> None:
        self.save_tasks(tasks)

    def update_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task = self._normalize_task(task)
        tasks = self._read_tasks()

        replaced = False
        for i, existing in enumerate(tasks):
            if self._task_name(existing) == self._task_name(task):
                tasks[i] = task
                replaced = True
                break

        if not replaced:
            tasks.append(task)

        self._write_tasks(tasks)
        return copy.deepcopy(task)

    def save_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return self.update_task(task)

    def upsert_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return self.update_task(task)

    def replace_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return self.update_task(task)

    def get_task(self, task_name: str) -> Optional[Dict[str, Any]]:
        tasks = self.get_all_tasks()
        for task in tasks:
            if self._task_name(task) == str(task_name):
                return copy.deepcopy(task)
        return None

    def get_current_task(self) -> Optional[Dict[str, Any]]:
        tasks = self.get_all_tasks()
        running_tasks = [t for t in tasks if t.get("status") == TASK_STATUS_RUNNING]
        if not running_tasks:
            return None

        running_tasks.sort(key=lambda t: self._task_name(t))
        return copy.deepcopy(running_tasks[0])

    # ------------------------------------------------------------------
    # 建立任務
    # ------------------------------------------------------------------

    def submit_task(
        self,
        goal: str,
        *,
        priority: int = 0,
        max_retries: int = 0,
        retry_delay: int = 0,
        timeout_ticks: int = 0,
        depends_on: Optional[List[str]] = None,
        simulate: str = "",
        required_ticks: int = 1,
    ) -> Dict[str, Any]:
        tasks = self._read_tasks()
        task_name = self._allocate_task_name(tasks)
        task_dir = os.path.join(self.workspace_dir, task_name)
        os.makedirs(task_dir, exist_ok=True)

        task: Dict[str, Any] = {
            "task_name": task_name,
            "goal": str(goal),
            "status": TASK_STATUS_QUEUED,
            "priority": int(priority),
            "retry_count": 0,
            "max_retries": int(max_retries),
            "retry_delay": int(retry_delay),
            "next_retry_tick": 0,
            "timeout_ticks": int(timeout_ticks),
            "wait_until_tick": 0,
            "depends_on": list(depends_on or []),
            "simulate": str(simulate or "").strip(),
            "required_ticks": max(1, int(required_ticks)),
            "created_tick": self._read_scheduler_tick(),
            "history": ["queued"],
            "last_error": None,
            "task_dir": task_dir,
            "workspace_dir": self.workspace_dir,
            "runtime_state_file": os.path.join(task_dir, "runtime_state.json"),
            "plan_file": os.path.join(task_dir, "plan.json"),
            "log_file": os.path.join(task_dir, "log.txt"),
        }

        self.task_runtime.ensure_runtime_state(task)
        task = self.task_runtime.sync_runtime_fields_back_to_task(task)

        tasks.append(self._normalize_task(task))
        self._write_tasks(tasks)

        return copy.deepcopy(task)

    # ------------------------------------------------------------------
    # 狀態操作
    # ------------------------------------------------------------------

    def pause_task(self, task_name: str) -> Dict[str, Any]:
        task = self._require_task(task_name)
        self.task_runtime.mark_paused(task)
        updated = self.task_runtime.sync_runtime_fields_back_to_task(task)
        self.update_task(updated)
        return updated

    def resume_task(self, task_name: str) -> Dict[str, Any]:
        task = self._require_task(task_name)
        self.task_runtime.resume_paused(task)
        updated = self.task_runtime.sync_runtime_fields_back_to_task(task)
        self.update_task(updated)
        return updated

    def cancel_task(self, task_name: str) -> Dict[str, Any]:
        task = self._require_task(task_name)
        current_tick = self._read_scheduler_tick()
        self.task_runtime.mark_canceled(task, current_tick=current_tick)
        updated = self.task_runtime.sync_runtime_fields_back_to_task(task)
        self.update_task(updated)
        return updated

    def set_task_priority(self, task_name: str, priority: int) -> Dict[str, Any]:
        task = self._require_task(task_name)
        state = self.task_runtime.ensure_runtime_state(task)
        state["priority"] = int(priority)
        self.task_runtime.save_runtime_state(task, state)

        updated = self.task_runtime.sync_runtime_fields_back_to_task(task)
        self.update_task(updated)
        return updated

    # ------------------------------------------------------------------
    # queue-list / 顯示層資料
    # ------------------------------------------------------------------

    def get_queue_snapshot(self) -> Dict[str, Any]:
        tasks = self.get_all_tasks()

        scheduler_state = self._read_scheduler_state()
        current_task_name = scheduler_state.get("current_task_name")
        tick = int(scheduler_state.get("tick", 0))

        queued = []
        paused = []
        waiting = []
        retrying = []
        blocked = []

        for task in tasks:
            status = task.get("status", TASK_STATUS_QUEUED)
            name = self._task_name(task)

            if status == TASK_STATUS_QUEUED:
                queued.append(name)
            elif status == TASK_STATUS_PAUSED:
                paused.append(name)
            elif status == TASK_STATUS_WAITING:
                waiting.append(name)
            elif status == TASK_STATUS_RETRYING:
                retrying.append(name)
            elif status == TASK_STATUS_BLOCKED:
                blocked.append(name)

        return {
            "tasks": copy.deepcopy(tasks),
            "scheduler_state": {
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
                "tick": tick,
                "has_work": bool(queued or paused or waiting or retrying or blocked),
            },
            "error": None,
        }

    def get_queue_list_rows(self) -> List[Dict[str, Any]]:
        tasks = self.get_all_tasks()
        rows: List[Dict[str, Any]] = []

        for task in tasks:
            history_list = task.get("history", [])
            history_text = " -> ".join(history_list) if history_list else ""

            rows.append(
                {
                    "task_name": self._task_name(task),
                    "status": task.get("status", TASK_STATUS_QUEUED),
                    "priority": int(task.get("priority", 0)),
                    "retry_count": int(task.get("retry_count", 0)),
                    "max_retries": int(task.get("max_retries", 0)),
                    "timeout_ticks": int(task.get("timeout_ticks", 0)),
                    "history": history_text,
                }
            )

        rows.sort(key=lambda r: r["task_name"])
        return rows

    # ------------------------------------------------------------------
    # 最小 execution hook
    # ------------------------------------------------------------------

    def run_task_one_tick(self, task: Dict[str, Any], current_tick: int) -> Dict[str, Any]:
        """
        給 scheduler 呼叫的最小 hook。
        目前先做保守行為：
        - simulate=fail / wait / block
        - required_ticks 決定幾輪後完成
        """
        state = self.task_runtime.ensure_runtime_state(task)

        progress_ticks = int(state.get("progress_ticks", 0))
        required_ticks = int(task.get("required_ticks", state.get("required_ticks", 1)))
        simulate = str(task.get("simulate", "")).strip().lower()

        progress_ticks += 1
        state["progress_ticks"] = progress_ticks
        state["required_ticks"] = required_ticks
        self.task_runtime.save_runtime_state(task, state)

        if simulate == "fail":
            return {
                "action": "fail",
                "message": "Simulated failure.",
                "error": "Simulated failure.",
            }

        if simulate == "wait":
            return {
                "action": "wait",
                "message": "Simulated waiting.",
                "delay": max(1, int(task.get("wait_delay", 1))),
            }

        if simulate == "block":
            return {
                "action": "block",
                "message": "Simulated blocked.",
            }

        if required_ticks <= 1 or progress_ticks >= required_ticks:
            return {
                "action": "finish",
                "message": "Task finished.",
            }

        return {
            "action": "requeue",
            "message": "Task requeued for next tick.",
        }

    # ------------------------------------------------------------------
    # scheduler state 檔案
    # ------------------------------------------------------------------

    def get_scheduler_state_file(self) -> str:
        return self.scheduler_state_file

    def _read_scheduler_state(self) -> Dict[str, Any]:
        if not os.path.exists(self.scheduler_state_file):
            return {
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

        try:
            with open(self.scheduler_state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {
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

        return data

    def _read_scheduler_tick(self) -> int:
        state = self._read_scheduler_state()
        return int(state.get("tick", 0))

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _require_task(self, task_name: str) -> Dict[str, Any]:
        task = self.get_task(task_name)
        if task is None:
            raise ValueError(f"Task not found: {task_name}")
        return task

    def _task_name(self, task: Dict[str, Any]) -> str:
        name = task.get("task_name") or task.get("id") or task.get("name")
        if not name:
            raise ValueError("Task is missing task_name/id/name.")
        return str(name)

    def _normalize_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_name = self._task_name(task)
        task_dir = task.get("task_dir") or os.path.join(self.workspace_dir, task_name)

        normalized: Dict[str, Any] = {
            "task_name": task_name,
            "goal": str(task.get("goal", "")),
            "status": str(task.get("status", TASK_STATUS_QUEUED)),
            "priority": int(task.get("priority", 0)),
            "retry_count": int(task.get("retry_count", 0)),
            "max_retries": int(task.get("max_retries", task.get("retry", 0))),
            "retry_delay": int(task.get("retry_delay", task.get("delay", 0))),
            "next_retry_tick": int(task.get("next_retry_tick", 0)),
            "timeout_ticks": int(task.get("timeout_ticks", task.get("timeout", 0))),
            "wait_until_tick": int(task.get("wait_until_tick", 0)),
            "depends_on": list(task.get("depends_on", task.get("dependencies", [])) or []),
            "simulate": str(task.get("simulate", "")).strip(),
            "required_ticks": max(1, int(task.get("required_ticks", 1))),
            "created_tick": int(task.get("created_tick", 0)),
            "history": list(task.get("history", ["queued"])),
            "last_error": task.get("last_error"),
            "task_dir": task_dir,
            "workspace_dir": self.workspace_dir,
            "runtime_state_file": task.get("runtime_state_file") or os.path.join(task_dir, "runtime_state.json"),
            "plan_file": task.get("plan_file") or os.path.join(task_dir, "plan.json"),
            "log_file": task.get("log_file") or os.path.join(task_dir, "log.txt"),
        }

        if not normalized["history"]:
            normalized["history"] = ["queued"]

        return normalized

    def _allocate_task_name(self, tasks: List[Dict[str, Any]]) -> str:
        used_numbers = []

        for task in tasks:
            name = str(task.get("task_name", ""))
            if name.startswith("task_"):
                suffix = name[5:]
                if suffix.isdigit():
                    used_numbers.append(int(suffix))

        next_number = 1
        if used_numbers:
            next_number = max(used_numbers) + 1

        return f"task_{next_number:04d}"