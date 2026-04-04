from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List, Optional

from core.tasks.task_paths import TaskPathManager


class TaskRepository:
    """
    ZERO Task Repository

    與目前主線 tasks.json 格式相容：

    {
      "tasks": [
        {...task1...},
        {...task2...}
      ]
    }

    職責：
    1. 管理 workspace/tasks.json
    2. 保留任務索引與 metadata
    3. 不負責保存大型 runtime 結果檔
    4. 與 TaskPathManager 統一路徑規則
    """

    def __init__(self, db_path: str = "workspace/tasks.json") -> None:
        self.db_path = os.path.abspath(db_path)
        self.workspace_root = os.path.dirname(self.db_path)
        self.path_manager = TaskPathManager(workspace_root=self.workspace_root)
        self.path_manager.ensure_workspace()

        self.tasks: List[Dict[str, Any]] = []
        self.load()

    # ============================================================
    # file io
    # ============================================================

    def load(self) -> None:
        if not os.path.exists(self.db_path):
            self.tasks = []
            self.save()
            return

        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            self.tasks = []
            return

        if isinstance(data, dict) and isinstance(data.get("tasks"), list):
            raw_tasks = data["tasks"]
        elif isinstance(data, list):
            raw_tasks = data
        else:
            raw_tasks = []

        normalized: List[Dict[str, Any]] = []
        for item in raw_tasks:
            if not isinstance(item, dict):
                continue
            try:
                normalized.append(self._normalize_task(item))
            except Exception:
                continue

        self.tasks = normalized

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        normalized = []
        for task in self.tasks:
            if not isinstance(task, dict):
                continue
            try:
                normalized.append(self._normalize_task(task))
            except Exception:
                continue

        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(
                {"tasks": normalized},
                f,
                ensure_ascii=False,
                indent=2,
            )

    # ============================================================
    # basic repo api
    # ============================================================

    def list_tasks(self) -> List[Dict[str, Any]]:
        return copy.deepcopy(self.tasks)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        task_id = str(task_id or "").strip()
        if not task_id:
            return None

        for task in self.tasks:
            if not isinstance(task, dict):
                continue

            current_id = (
                task.get("task_id")
                or task.get("task_name")
                or task.get("id")
            )
            if str(current_id).strip() == task_id:
                return copy.deepcopy(task)

        return None

    def add_task(self, task: Dict[str, Any]) -> bool:
        if not isinstance(task, dict):
            return False

        normalized = self._normalize_task(task)
        task_id = normalized["task_id"]

        existed = self._find_task_ref(task_id)
        if existed is not None:
            return False

        self.tasks.append(normalized)
        self.save()
        return True

    def create_task(self, task: Dict[str, Any]) -> bool:
        return self.add_task(task)

    def upsert_task(self, task: Dict[str, Any]) -> bool:
        if not isinstance(task, dict):
            return False

        normalized = self._normalize_task(task)
        task_id = normalized["task_id"]

        for i, existing in enumerate(self.tasks):
            existing_id = (
                existing.get("task_id")
                or existing.get("task_name")
                or existing.get("id")
            )
            if str(existing_id).strip() == task_id:
                self.tasks[i] = normalized
                self.save()
                return True

        self.tasks.append(normalized)
        self.save()
        return True

    def delete_task(self, task_id: str) -> bool:
        task_id = str(task_id or "").strip()
        if not task_id:
            return False

        original_len = len(self.tasks)
        self.tasks = [
            task for task in self.tasks
            if str(
                task.get("task_id")
                or task.get("task_name")
                or task.get("id")
                or ""
            ).strip() != task_id
        ]

        changed = len(self.tasks) != original_len
        if changed:
            self.save()
        return changed

    # ============================================================
    # scheduler-compatible api
    # ============================================================

    def set_task_status(self, task_id: str, status: str) -> bool:
        task = self._find_task_ref(task_id)
        if task is None:
            return False

        task["status"] = str(status)
        self.save()
        return True

    def update_task_field(self, task_id: str, field_name: str, value: Any) -> bool:
        task = self._find_task_ref(task_id)
        if task is None:
            return False

        task[field_name] = copy.deepcopy(value)
        task = self._normalize_task(task)

        for i, item in enumerate(self.tasks):
            current_id = (
                item.get("task_id")
                or item.get("task_name")
                or item.get("id")
            )
            if str(current_id).strip() == task_id:
                self.tasks[i] = task
                self.save()
                return True

        return False

    def replace_task(self, task_id: str, new_task: Dict[str, Any]) -> bool:
        if not isinstance(new_task, dict):
            return False

        normalized = self._normalize_task(new_task)

        for i, item in enumerate(self.tasks):
            current_id = (
                item.get("task_id")
                or item.get("task_name")
                or item.get("id")
            )
            if str(current_id).strip() == str(task_id).strip():
                self.tasks[i] = normalized
                self.save()
                return True

        return False

    # ============================================================
    # normalization
    # ============================================================

    def _normalize_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(task, dict):
            raise TypeError("task must be dict")

        task_id = str(
            task.get("task_id")
            or task.get("task_name")
            or task.get("id")
            or ""
        ).strip()

        if not task_id:
            raise ValueError("task missing task_id/task_name/id")

        enriched = self.path_manager.enrich_task(task)

        steps = enriched.get("steps", [])
        if not isinstance(steps, list):
            steps = []

        results = enriched.get("results", [])
        if not isinstance(results, list):
            results = []

        execution_log = enriched.get("execution_log", [])
        if not isinstance(execution_log, list):
            execution_log = []

        history = enriched.get("history", ["queued"])
        if isinstance(history, str):
            history = [history]
        elif not isinstance(history, list):
            history = ["queued"]

        normalized = {
            "task_id": task_id,
            "task_name": task_id,
            "title": str(enriched.get("title", enriched.get("goal", ""))),
            "goal": str(enriched.get("goal", "")),
            "status": str(enriched.get("status", "queued")),
            "priority": int(enriched.get("priority", 0)),
            "current_step_index": int(enriched.get("current_step_index", 0)),
            "steps": copy.deepcopy(steps),
            "steps_total": int(enriched.get("steps_total", len(steps))),
            "results": copy.deepcopy(results),
            "execution_log": copy.deepcopy(execution_log),
            "final_answer": str(enriched.get("final_answer", "")),
            "retry_count": int(enriched.get("retry_count", 0)),
            "max_retries": int(enriched.get("max_retries", 0)),
            "retry_delay": int(enriched.get("retry_delay", 0)),
            "timeout_ticks": int(enriched.get("timeout_ticks", 0)),
            "created_at": enriched.get("created_at"),
            "created_tick": int(enriched.get("created_tick", 0)),
            "last_run_tick": enriched.get("last_run_tick"),
            "last_failure_tick": enriched.get("last_failure_tick"),
            "finished_tick": enriched.get("finished_tick"),
            "depends_on": copy.deepcopy(enriched.get("depends_on", [])) if isinstance(enriched.get("depends_on", []), list) else [],
            "blocked_reason": str(enriched.get("blocked_reason", "")),
            "failure_type": enriched.get("failure_type"),
            "failure_message": enriched.get("failure_message"),
            "last_error": enriched.get("last_error"),
            "cancel_requested": bool(enriched.get("cancel_requested", False)),
            "cancel_reason": str(enriched.get("cancel_reason", "")),
            "planner_result": copy.deepcopy(enriched.get("planner_result", {})) if isinstance(enriched.get("planner_result", {}), dict) else {},
            "replan_count": int(enriched.get("replan_count", 0)),
            "replanned": bool(enriched.get("replanned", False)),
            "replan_reason": str(enriched.get("replan_reason", "")),
            "max_replans": int(enriched.get("max_replans", 1)),
            "history": copy.deepcopy(history),
            "workspace_dir": str(enriched.get("workspace_dir", "")),
            "task_dir": str(enriched.get("task_dir", "")),
            "plan_file": str(enriched.get("plan_file", "")),
            "runtime_state_file": str(enriched.get("runtime_state_file", "")),
            "execution_log_file": str(enriched.get("execution_log_file", "")),
            "result_file": str(enriched.get("result_file", "")),
            "log_file": str(enriched.get("log_file", "")),
        }

        return normalized

    # ============================================================
    # internal helpers
    # ============================================================

    def _find_task_ref(self, task_id: str) -> Optional[Dict[str, Any]]:
        task_id = str(task_id or "").strip()
        if not task_id:
            return None

        for task in self.tasks:
            if not isinstance(task, dict):
                continue

            current_id = (
                task.get("task_id")
                or task.get("task_name")
                or task.get("id")
            )
            if str(current_id).strip() == task_id:
                return task

        return None

    # ============================================================
    # debug / helper
    # ============================================================

    def rebuild_index(self) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        for task in self.tasks:
            if not isinstance(task, dict):
                continue
            task_id = (
                task.get("task_id")
                or task.get("task_name")
                or task.get("id")
            )
            if task_id:
                result[str(task_id)] = copy.deepcopy(task)
        return result

    def dump_summary(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for task in self.tasks:
            if not isinstance(task, dict):
                continue
            items.append(
                {
                    "task_id": task.get("task_id") or task.get("task_name") or task.get("id"),
                    "status": task.get("status"),
                    "current_step_index": task.get("current_step_index"),
                    "steps_total": task.get("steps_total"),
                    "priority": task.get("priority"),
                    "title": task.get("title"),
                    "task_dir": task.get("task_dir"),
                }
            )
        return items