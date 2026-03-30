from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


class ProjectMemory:
    """
    Project Memory / Long-term Memory

    收集所有 task 的 summary，建立 project_memory.json
    """

    def __init__(self, workspace_root: Path | str) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.project_memory_file = self.workspace_root / "project_memory.json"

    # =========================================================
    # Public
    # =========================================================

    def update_from_task_summary(self, task_name: str) -> None:
        summary_file = self.workspace_root / task_name / "summary.json"
        if not summary_file.exists():
            return

        with open(summary_file, "r", encoding="utf-8") as f:
            summary = json.load(f)

        project_memory = self._load_project_memory()

        tasks = project_memory.get("tasks", [])
        tasks.append(summary)
        project_memory["tasks"] = tasks

        project_memory["task_count"] = len(tasks)
        project_memory["last_task"] = task_name

        self._save_project_memory(project_memory)

    def get_recent_tasks(self, limit: int = 5) -> List[Dict[str, Any]]:
        memory = self._load_project_memory()
        tasks = memory.get("tasks", [])
        return tasks[-limit:]

    # =========================================================
    # Internal
    # =========================================================

    def _load_project_memory(self) -> Dict[str, Any]:
        if not self.project_memory_file.exists():
            return {
                "task_count": 0,
                "last_task": None,
                "tasks": [],
            }

        with open(self.project_memory_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_project_memory(self, memory: Dict[str, Any]) -> None:
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        with open(self.project_memory_file, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2, ensure_ascii=False)