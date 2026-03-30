from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional


class MemoryEngine:
    """
    MemoryEngine
    ----------------
    功能：
    - 儲存任務記憶
    - 儲存 reflection 記憶
    - 儲存錯誤記憶
    - 搜尋歷史記憶
    - 提供給 planner / agent 使用
    """

    def __init__(self, memory_file: str = "data/memory/memory.json") -> None:
        self.memory_file = memory_file
        os.makedirs(os.path.dirname(memory_file), exist_ok=True)
        self.memory = self._load_memory()

    # =========================================================
    # Memory Load / Save
    # =========================================================

    def _load_memory(self) -> Dict[str, Any]:
        if not os.path.exists(self.memory_file):
            return {
                "tasks": [],
                "reflections": [],
                "errors": [],
                "knowledge": [],
            }

        try:
            with open(self.memory_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {
                "tasks": [],
                "reflections": [],
                "errors": [],
                "knowledge": [],
            }

    def _save_memory(self) -> None:
        with open(self.memory_file, "w", encoding="utf-8") as f:
            json.dump(self.memory, f, ensure_ascii=False, indent=2)

    # =========================================================
    # Task Memory
    # =========================================================

    def add_task_memory(
        self,
        task_id: str,
        goal: str,
        success: bool,
        summary: str,
    ) -> None:
        record = {
            "task_id": task_id,
            "goal": goal,
            "success": success,
            "summary": summary,
            "created_at": self._now(),
        }

        self.memory["tasks"].append(record)
        self._save_memory()

    # =========================================================
    # Reflection Memory
    # =========================================================

    def add_reflection_memory(
        self,
        task_id: str,
        score: int,
        status: str,
        summary: str,
    ) -> None:
        record = {
            "task_id": task_id,
            "score": score,
            "status": status,
            "summary": summary,
            "created_at": self._now(),
        }

        self.memory["reflections"].append(record)
        self._save_memory()

    # =========================================================
    # Error Memory
    # =========================================================

    def add_error_memory(
        self,
        task_id: str,
        error: str,
    ) -> None:
        record = {
            "task_id": task_id,
            "error": error,
            "created_at": self._now(),
        }

        self.memory["errors"].append(record)
        self._save_memory()

    # =========================================================
    # Knowledge Memory
    # =========================================================

    def add_knowledge(
        self,
        topic: str,
        content: str,
    ) -> None:
        record = {
            "topic": topic,
            "content": content,
            "created_at": self._now(),
        }

        self.memory["knowledge"].append(record)
        self._save_memory()

    # =========================================================
    # Search
    # =========================================================

    def search_tasks(self, keyword: str) -> List[Dict[str, Any]]:
        return [
            t for t in self.memory["tasks"]
            if keyword.lower() in t.get("goal", "").lower()
        ]

    def search_errors(self, keyword: str) -> List[Dict[str, Any]]:
        return [
            e for e in self.memory["errors"]
            if keyword.lower() in e.get("error", "").lower()
        ]

    def search_knowledge(self, keyword: str) -> List[Dict[str, Any]]:
        return [
            k for k in self.memory["knowledge"]
            if keyword.lower() in k.get("topic", "").lower()
            or keyword.lower() in k.get("content", "").lower()
        ]

    # =========================================================
    # Stats
    # =========================================================

    def get_stats(self) -> Dict[str, Any]:
        total_tasks = len(self.memory["tasks"])
        success_tasks = len([t for t in self.memory["tasks"] if t.get("success")])
        failed_tasks = total_tasks - success_tasks

        avg_score = 0
        reflections = self.memory["reflections"]
        if reflections:
            avg_score = sum(r.get("score", 0) for r in reflections) / len(reflections)

        return {
            "total_tasks": total_tasks,
            "success_tasks": success_tasks,
            "failed_tasks": failed_tasks,
            "avg_reflection_score": round(avg_score, 2),
            "error_count": len(self.memory["errors"]),
            "knowledge_count": len(self.memory["knowledge"]),
        }

    # =========================================================
    # Helpers
    # =========================================================

    def _now(self) -> str:
        return datetime.utcnow().isoformat() + "Z"


if __name__ == "__main__":
    memory = MemoryEngine()

    memory.add_task_memory(
        task_id="demo_task",
        goal="查詢天氣",
        success=True,
        summary="任務成功完成",
    )

    memory.add_reflection_memory(
        task_id="demo_task",
        score=88,
        status="good",
        summary="流程正常",
    )

    memory.add_error_memory(
        task_id="demo_task",
        error="tool timeout",
    )

    memory.add_knowledge(
        topic="weather api",
        content="可以使用 open-meteo API 查詢天氣",
    )

    print(memory.get_stats())