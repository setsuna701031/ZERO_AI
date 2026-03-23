from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class TaskManager:
    """
    ZERO Task Manager

    負責：
    - 建立 task_xxxx 資料夾
    - 維護 task_memory.json
    - 提供正式任務結構
    - 記錄 plan / steps / result
    - 相容舊版 task_memory.json 格式
    """

    def __init__(self, workspace_root: Path | str) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

        self.memory_file = self.workspace_root / "task_memory.json"

        if not self.memory_file.exists():
            self._save_memory(self._default_memory())

    # =========================================================
    # Task Creation / Query / Update
    # =========================================================

    def create_task(self, goal: str) -> Dict[str, Any]:
        clean_goal = str(goal).strip()
        if not clean_goal:
            raise ValueError("goal cannot be empty.")

        memory = self._load_memory()

        task_id = int(memory.get("last_task_id", 0)) + 1
        task_name = f"task_{task_id:04d}"
        task_dir = self.workspace_root / task_name
        task_dir.mkdir(parents=True, exist_ok=True)

        created_at = self._utc_now_iso()

        task_info = {
            "task_id": task_id,
            "task_name": task_name,
            "input": clean_goal,
            "goal": clean_goal,
            "task_dir": str(task_dir),
            "status": "created",
            "created_at": created_at,
            "updated_at": created_at,
        }

        tasks = memory.get("tasks", [])
        if not isinstance(tasks, list):
            tasks = []

        tasks.append(task_info)
        memory["tasks"] = tasks
        memory["last_task_id"] = task_id

        self._save_memory(memory)
        return task_info

    def get_task(self, task_name: str) -> Optional[Dict[str, Any]]:
        clean_name = str(task_name).strip()
        if not clean_name:
            return None

        memory = self._load_memory()
        tasks = memory.get("tasks", [])

        if not isinstance(tasks, list):
            return None

        for item in tasks:
            if not isinstance(item, dict):
                continue
            if str(item.get("task_name", "")).strip() == clean_name:
                return item

        return None

    def list_tasks(self) -> List[Dict[str, Any]]:
        memory = self._load_memory()
        tasks = memory.get("tasks", [])

        if not isinstance(tasks, list):
            return []

        normalized_tasks: List[Dict[str, Any]] = []
        for item in tasks:
            normalized_item = self._normalize_task_item(item)
            if normalized_item is not None:
                normalized_tasks.append(normalized_item)

        return normalized_tasks

    def update_task_status(self, task_name: str, status: str) -> Dict[str, Any]:
        clean_name = str(task_name).strip()
        clean_status = str(status).strip()

        if not clean_name:
            raise ValueError("task_name cannot be empty.")
        if not clean_status:
            raise ValueError("status cannot be empty.")

        memory = self._load_memory()
        tasks = memory.get("tasks", [])

        if not isinstance(tasks, list):
            tasks = []

        updated = None
        now = self._utc_now_iso()

        for item in tasks:
            if not isinstance(item, dict):
                continue
            if str(item.get("task_name", "")).strip() == clean_name:
                item["status"] = clean_status
                item["updated_at"] = now
                updated = item
                break

        if updated is None:
            raise ValueError(f"Task not found: {clean_name}")

        memory["tasks"] = tasks
        self._save_memory(memory)
        return updated

    # =========================================================
    # Plan / Step / Result logging
    # =========================================================

    def save_plan(self, task_name: str, plan: Dict[str, Any]) -> None:
        task_dir = self._ensure_task_dir(task_name)
        plan_file = task_dir / "plan.json"
        self._save_json(plan_file, plan)

    def save_step(self, task_name: str, step_index: int, data: Dict[str, Any]) -> None:
        task_dir = self._ensure_task_dir(task_name)
        step_file = task_dir / f"step_{step_index:02d}.json"
        self._save_json(step_file, data)

    def save_result(self, task_name: str, result: Dict[str, Any]) -> None:
        task_dir = self._ensure_task_dir(task_name)
        result_file = task_dir / "result.json"
        self._save_json(result_file, result)

    # =========================================================
    # Memory file
    # =========================================================

    def _default_memory(self) -> Dict[str, Any]:
        return {
            "last_task_id": self._scan_existing_task_max_id(),
            "tasks": [],
        }

    def _load_memory(self) -> Dict[str, Any]:
        if not self.memory_file.exists():
            memory = self._default_memory()
            self._save_memory(memory)
            return memory

        try:
            with open(self.memory_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            memory = self._default_memory()
            self._save_memory(memory)
            return memory

        normalized = self._normalize_memory(raw)
        self._save_memory(normalized)
        return normalized

    def _save_memory(self, data: Dict[str, Any]) -> None:
        normalized = self._normalize_memory(data)
        with open(self.memory_file, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2, ensure_ascii=False)

    def _normalize_memory(self, raw: Any) -> Dict[str, Any]:
        """
        相容幾種舊格式：
        1. dict 正常格式
        2. list -> 視為 tasks 清單
        3. 其他異常 -> 重建
        """
        max_existing_id = self._scan_existing_task_max_id()

        if isinstance(raw, dict):
            last_task_id = raw.get("last_task_id", 0)
            tasks = raw.get("tasks", [])

            if not isinstance(tasks, list):
                tasks = []

            normalized_tasks = []
            max_task_id_in_tasks = 0

            for item in tasks:
                normalized_item = self._normalize_task_item(item)
                if normalized_item is None:
                    continue
                normalized_tasks.append(normalized_item)
                max_task_id_in_tasks = max(max_task_id_in_tasks, normalized_item["task_id"])

            safe_last_task_id = self._safe_int(last_task_id, 0)
            safe_last_task_id = max(safe_last_task_id, max_task_id_in_tasks, max_existing_id)

            return {
                "last_task_id": safe_last_task_id,
                "tasks": normalized_tasks,
            }

        if isinstance(raw, list):
            normalized_tasks = []
            max_task_id_in_tasks = 0

            for item in raw:
                normalized_item = self._normalize_task_item(item)
                if normalized_item is None:
                    continue
                normalized_tasks.append(normalized_item)
                max_task_id_in_tasks = max(max_task_id_in_tasks, normalized_item["task_id"])

            safe_last_task_id = max(max_task_id_in_tasks, max_existing_id)

            return {
                "last_task_id": safe_last_task_id,
                "tasks": normalized_tasks,
            }

        return {
            "last_task_id": max_existing_id,
            "tasks": [],
        }

    def _normalize_task_item(self, item: Any) -> Dict[str, Any] | None:
        if not isinstance(item, dict):
            return None

        task_name = str(item.get("task_name", "")).strip()
        task_id = item.get("task_id")

        if not task_name:
            if isinstance(task_id, int):
                task_name = f"task_{task_id:04d}"
            else:
                return None

        parsed_id = self._extract_task_id_from_name(task_name)
        safe_task_id = self._safe_int(task_id, parsed_id if parsed_id is not None else 0)

        if safe_task_id <= 0 and parsed_id is not None:
            safe_task_id = parsed_id

        if safe_task_id <= 0:
            return None

        canonical_task_name = f"task_{safe_task_id:04d}"
        task_dir = str(self.workspace_root / canonical_task_name)

        goal = str(item.get("goal", item.get("input", "")))
        input_text = str(item.get("input", goal))

        created_at = self._safe_str(
            item.get("created_at", ""),
            default=""
        )
        updated_at = self._safe_str(
            item.get("updated_at", created_at),
            default=created_at
        )

        return {
            "task_id": safe_task_id,
            "task_name": canonical_task_name,
            "input": input_text,
            "goal": goal,
            "task_dir": str(item.get("task_dir", task_dir)),
            "status": str(item.get("status", "unknown")),
            "created_at": created_at,
            "updated_at": updated_at,
        }

    # =========================================================
    # Helpers
    # =========================================================

    def _ensure_task_dir(self, task_name: str) -> Path:
        clean_name = str(task_name).strip()
        if not clean_name:
            raise ValueError("task_name cannot be empty.")

        task_dir = self.workspace_root / clean_name
        task_dir.mkdir(parents=True, exist_ok=True)
        return task_dir

    def _save_json(self, path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default

    def _safe_str(self, value: Any, default: str = "") -> str:
        try:
            if value is None:
                return default
            return str(value)
        except Exception:
            return default

    def _extract_task_id_from_name(self, task_name: str) -> int | None:
        if not isinstance(task_name, str):
            return None

        task_name = task_name.strip()
        if not task_name.startswith("task_"):
            return None

        suffix = task_name[5:]
        if not suffix.isdigit():
            return None

        return int(suffix)

    def _scan_existing_task_max_id(self) -> int:
        max_id = 0

        for item in self.workspace_root.iterdir():
            if not item.is_dir():
                continue

            parsed_id = self._extract_task_id_from_name(item.name)
            if parsed_id is not None:
                max_id = max(max_id, parsed_id)

        return max_id

    def _utc_now_iso(self) -> str:
        return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"