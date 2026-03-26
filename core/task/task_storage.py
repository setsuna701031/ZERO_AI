# core/task/task_storage.py

import json
import os
from typing import Optional

from core.task.task_models import TaskRecord


class TaskStorage:
    """
    Task JSON 儲存與載入
    """

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root = workspace_root
        self.tasks_root = os.path.join(self.workspace_root, "tasks")
        os.makedirs(self.tasks_root, exist_ok=True)

    def get_task_dir(self, task_id: str) -> str:
        return os.path.join(self.tasks_root, task_id)

    def get_task_file(self, task_id: str) -> str:
        return os.path.join(self.get_task_dir(task_id), "task.json")

    def task_exists(self, task_id: str) -> bool:
        return os.path.exists(self.get_task_file(task_id))

    def save_task(self, task: TaskRecord) -> None:
        task_dir = self.get_task_dir(task.task_id)
        os.makedirs(task_dir, exist_ok=True)

        task_file = self.get_task_file(task.task_id)

        with open(task_file, "w", encoding="utf-8") as f:
            json.dump(task.to_dict(), f, indent=2, ensure_ascii=False)

    def load_task(self, task_id: str) -> Optional[TaskRecord]:
        task_file = self.get_task_file(task_id)

        if not os.path.exists(task_file):
            return None

        with open(task_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        return TaskRecord.from_dict(data)

    def list_tasks(self) -> list[str]:
        if not os.path.exists(self.tasks_root):
            return []

        return [
            name for name in os.listdir(self.tasks_root)
            if os.path.isdir(os.path.join(self.tasks_root, name))
        ]