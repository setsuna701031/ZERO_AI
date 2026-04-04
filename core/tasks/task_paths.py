from __future__ import annotations

import os
from typing import Dict


class TaskPathManager:
    """
    統一管理 ZERO Task OS 的 workspace / task 路徑。

    原則：
    - workspace/tasks.json 是全域任務索引
    - workspace/tasks/<task_id>/... 是單一任務工作目錄
    - 其他模組不要自己手拼路徑，全部走這個 manager
    """

    def __init__(self, workspace_root: str = "workspace") -> None:
        self.workspace_root = os.path.abspath(workspace_root)
        self.tasks_root = os.path.join(self.workspace_root, "tasks")
        self.tasks_index_file = os.path.join(self.workspace_root, "tasks.json")
        self.scheduler_state_file = os.path.join(self.workspace_root, "scheduler_state.json")
        self.runtime_root = os.path.join(self.workspace_root, "runtime")
        self.logs_root = os.path.join(self.workspace_root, "logs")
        self.memory_root = os.path.join(self.workspace_root, "memory")
        self.knowledge_root = os.path.join(self.workspace_root, "knowledge")
        self.cache_root = os.path.join(self.workspace_root, "cache")

    # ============================================================
    # workspace-level paths
    # ============================================================

    def ensure_workspace(self) -> None:
        os.makedirs(self.workspace_root, exist_ok=True)
        os.makedirs(self.tasks_root, exist_ok=True)
        os.makedirs(self.runtime_root, exist_ok=True)
        os.makedirs(self.logs_root, exist_ok=True)
        os.makedirs(self.memory_root, exist_ok=True)
        os.makedirs(self.knowledge_root, exist_ok=True)
        os.makedirs(self.cache_root, exist_ok=True)

    def get_workspace_paths(self) -> Dict[str, str]:
        return {
            "workspace_root": self.workspace_root,
            "tasks_root": self.tasks_root,
            "tasks_index_file": self.tasks_index_file,
            "scheduler_state_file": self.scheduler_state_file,
            "runtime_root": self.runtime_root,
            "logs_root": self.logs_root,
            "memory_root": self.memory_root,
            "knowledge_root": self.knowledge_root,
            "cache_root": self.cache_root,
        }

    # ============================================================
    # task-level paths
    # ============================================================

    def task_dir(self, task_id: str) -> str:
        return os.path.join(self.tasks_root, str(task_id).strip())

    def plan_file(self, task_id: str) -> str:
        return os.path.join(self.task_dir(task_id), "plan.json")

    def runtime_state_file(self, task_id: str) -> str:
        return os.path.join(self.task_dir(task_id), "runtime_state.json")

    def result_file(self, task_id: str) -> str:
        return os.path.join(self.task_dir(task_id), "result.json")

    def execution_log_file(self, task_id: str) -> str:
        return os.path.join(self.task_dir(task_id), "execution_log.json")

    def task_snapshot_file(self, task_id: str) -> str:
        return os.path.join(self.task_dir(task_id), "task.json")

    def task_log_file(self, task_id: str) -> str:
        return os.path.join(self.task_dir(task_id), "task.log")

    def runner_trace_file(self, task_id: str) -> str:
        return os.path.join(self.task_dir(task_id), "task_runner_trace.log")

    def runtime_trace_file(self, task_id: str) -> str:
        return os.path.join(self.task_dir(task_id), "task_runtime_trace.log")

    def file_in_task_dir(self, task_id: str, relative_path: str) -> str:
        cleaned = str(relative_path).replace("/", os.sep).replace("\\", os.sep)
        return os.path.join(self.task_dir(task_id), cleaned)

    def get_task_paths(self, task_id: str) -> Dict[str, str]:
        task_id = str(task_id).strip()
        return {
            "task_id": task_id,
            "task_dir": self.task_dir(task_id),
            "plan_file": self.plan_file(task_id),
            "runtime_state_file": self.runtime_state_file(task_id),
            "result_file": self.result_file(task_id),
            "execution_log_file": self.execution_log_file(task_id),
            "task_file": self.task_snapshot_file(task_id),
            "log_file": self.task_log_file(task_id),
            "runner_trace_file": self.runner_trace_file(task_id),
            "runtime_trace_file": self.runtime_trace_file(task_id),
        }

    def ensure_task_dir(self, task_id: str) -> str:
        task_dir = self.task_dir(task_id)
        os.makedirs(task_dir, exist_ok=True)
        return task_dir

    def ensure_task_paths(self, task_id: str) -> Dict[str, str]:
        self.ensure_workspace()
        self.ensure_task_dir(task_id)
        return self.get_task_paths(task_id)

    # ============================================================
    # task helpers
    # ============================================================

    def enrich_task(self, task: Dict[str, object]) -> Dict[str, object]:
        """
        把路徑欄位補到 task dict 裡。
        不修改外部傳入物件，回傳新 dict。
        """
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

        enriched = dict(task)
        paths = self.ensure_task_paths(task_id)

        enriched["task_id"] = task_id
        enriched["task_name"] = task_id
        enriched["workspace_dir"] = self.tasks_root
        enriched["task_dir"] = paths["task_dir"]
        enriched["plan_file"] = paths["plan_file"]
        enriched["runtime_state_file"] = paths["runtime_state_file"]
        enriched["result_file"] = paths["result_file"]
        enriched["execution_log_file"] = paths["execution_log_file"]
        enriched["log_file"] = paths["log_file"]

        return enriched