from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.path_manager import PathManager


class Workspace:
    """
    ZERO Workspace System v2

    作用：
    1. 建立任務工作區
    2. 列出任務
    3. 寫入任務筆記
    4. 寫入任務日誌
    5. 取得任務資訊與路徑

    設計原則：
    - Workspace 不負責決定 workspace root 在哪
    - workspace 路徑規則全部交給 PathManager
    - Workspace 只負責 task 結構與 task 內容
    """

    def __init__(
        self,
        path_manager: Optional[PathManager] = None,
        base_dir: Optional[str] = None,
    ) -> None:
        """
        優先使用 path_manager。
        若未傳入，才用 base_dir 建立預設 PathManager。

        這樣可以：
        1. 正式接 PathManager
        2. 保留舊呼叫方式的相容性
        """
        if path_manager is not None:
            self.path_manager = path_manager
        else:
            self.path_manager = PathManager(base_dir=base_dir)

        self.workspace_root: Path = self.path_manager.workspace_root

    # =========================
    # Public API
    # =========================

    def create_task(self, task_name: str, description: str = "") -> Dict[str, Any]:
        """
        建立新任務工作區

        回傳範例：
        {
            "ok": True,
            "task_id": "task_0001",
            "task_name": "refactor agent loop",
            "task_dir": "E:\\zero_ai\\workspace\\task_0001"
        }
        """
        normalized_name = self._normalize_task_name(task_name)
        next_task_id = self._get_next_task_id()
        task_dir = self.path_manager.ensure_task_dir(next_task_id)

        files_dir = self.path_manager.task_subdir(next_task_id, "files")
        output_dir = self.path_manager.task_subdir(next_task_id, "output")

        files_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        now = self._now_str()
        task_data: Dict[str, Any] = {
            "task_id": next_task_id,
            "task_name": normalized_name,
            "original_task_name": task_name,
            "description": description,
            "status": "created",
            "created_at": now,
            "updated_at": now,
        }

        self._write_text(self.path_manager.task_file(next_task_id, "plan.txt"), "")
        self._write_text(self.path_manager.task_file(next_task_id, "notes.txt"), "")
        self._write_text(self.path_manager.task_file(next_task_id, "logs.txt"), "")
        self._write_json(self.path_manager.task_file(next_task_id, "task.json"), task_data)

        return {
            "ok": True,
            "task_id": next_task_id,
            "task_name": normalized_name,
            "task_dir": str(task_dir),
        }

    def list_tasks(self) -> Dict[str, Any]:
        """
        列出所有任務
        """
        tasks: List[Dict[str, Any]] = []

        if not self.workspace_root.exists():
            return {
                "ok": True,
                "count": 0,
                "tasks": []
            }

        for item in sorted(self.workspace_root.iterdir()):
            if not item.is_dir():
                continue
            if not re.match(r"^task_\d{4}$", item.name):
                continue

            task_json_path = item / "task.json"
            if task_json_path.exists():
                task_data = self._read_json(task_json_path)
                if isinstance(task_data, dict):
                    tasks.append({
                        "task_id": task_data.get("task_id", item.name),
                        "task_name": task_data.get("task_name", ""),
                        "status": task_data.get("status", "unknown"),
                        "created_at": task_data.get("created_at", ""),
                        "updated_at": task_data.get("updated_at", ""),
                        "task_dir": str(item),
                    })
                else:
                    tasks.append({
                        "task_id": item.name,
                        "task_name": "",
                        "status": "invalid_task_json",
                        "created_at": "",
                        "updated_at": "",
                        "task_dir": str(item),
                    })
            else:
                tasks.append({
                    "task_id": item.name,
                    "task_name": "",
                    "status": "missing_task_json",
                    "created_at": "",
                    "updated_at": "",
                    "task_dir": str(item),
                })

        return {
            "ok": True,
            "count": len(tasks),
            "tasks": tasks
        }

    def get_task(self, task_id: str) -> Dict[str, Any]:
        """
        取得單一任務資訊
        """
        normalized_task_id = self.path_manager.normalize_task_id(task_id)
        task_dir = self.path_manager.task_path(normalized_task_id)

        if not task_dir.exists() or not task_dir.is_dir():
            return {
                "ok": False,
                "error": "task_not_found",
                "task_id": normalized_task_id
            }

        task_json_path = self.path_manager.task_file(normalized_task_id, "task.json")
        if not task_json_path.exists():
            return {
                "ok": False,
                "error": "task_json_not_found",
                "task_id": normalized_task_id,
                "task_dir": str(task_dir)
            }

        task_data = self._read_json(task_json_path)
        if not isinstance(task_data, dict):
            return {
                "ok": False,
                "error": "task_json_invalid",
                "task_id": normalized_task_id,
                "task_dir": str(task_dir)
            }

        return {
            "ok": True,
            "task": task_data,
            "task_dir": str(task_dir),
            "notes_path": str(self.path_manager.task_file(normalized_task_id, "notes.txt")),
            "logs_path": str(self.path_manager.task_file(normalized_task_id, "logs.txt")),
            "plan_path": str(self.path_manager.task_file(normalized_task_id, "plan.txt")),
            "files_dir": str(self.path_manager.task_subdir(normalized_task_id, "files")),
            "output_dir": str(self.path_manager.task_subdir(normalized_task_id, "output")),
        }

    def get_task_path(self, task_id: str) -> Dict[str, Any]:
        """
        取得任務路徑
        """
        normalized_task_id = self.path_manager.normalize_task_id(task_id)
        task_dir = self.path_manager.task_path(normalized_task_id)

        if not task_dir.exists() or not task_dir.is_dir():
            return {
                "ok": False,
                "error": "task_not_found",
                "task_id": normalized_task_id
            }

        return {
            "ok": True,
            "task_id": normalized_task_id,
            "task_dir": str(task_dir)
        }

    def write_note(self, task_id: str, text: str) -> Dict[str, Any]:
        """
        寫入任務筆記（append）
        """
        normalized_task_id = self.path_manager.normalize_task_id(task_id)
        task_dir = self.path_manager.task_path(normalized_task_id)

        if not task_dir.exists() or not task_dir.is_dir():
            return {
                "ok": False,
                "error": "task_not_found",
                "task_id": normalized_task_id
            }

        notes_path = self.path_manager.task_file(normalized_task_id, "notes.txt")
        timestamp = self._now_str()
        entry = f"[{timestamp}] {text}\n"

        self._append_text(notes_path, entry)
        self._touch_task_updated_at(normalized_task_id)

        return {
            "ok": True,
            "task_id": normalized_task_id,
            "notes_path": str(notes_path),
            "written_text": text
        }

    def read_notes(self, task_id: str) -> Dict[str, Any]:
        """
        讀取任務筆記
        """
        normalized_task_id = self.path_manager.normalize_task_id(task_id)
        task_dir = self.path_manager.task_path(normalized_task_id)

        if not task_dir.exists() or not task_dir.is_dir():
            return {
                "ok": False,
                "error": "task_not_found",
                "task_id": normalized_task_id
            }

        notes_path = self.path_manager.task_file(normalized_task_id, "notes.txt")
        if not notes_path.exists():
            return {
                "ok": False,
                "error": "notes_not_found",
                "task_id": normalized_task_id
            }

        content = self._read_text(notes_path)
        return {
            "ok": True,
            "task_id": normalized_task_id,
            "notes_path": str(notes_path),
            "content": content
        }

    def log(self, task_id: str, text: str, level: str = "INFO") -> Dict[str, Any]:
        """
        寫入任務日誌（append）
        """
        normalized_task_id = self.path_manager.normalize_task_id(task_id)
        task_dir = self.path_manager.task_path(normalized_task_id)

        if not task_dir.exists() or not task_dir.is_dir():
            return {
                "ok": False,
                "error": "task_not_found",
                "task_id": normalized_task_id
            }

        logs_path = self.path_manager.task_file(normalized_task_id, "logs.txt")
        timestamp = self._now_str()
        safe_level = (level or "INFO").upper().strip() or "INFO"
        entry = f"[{timestamp}] [{safe_level}] {text}\n"

        self._append_text(logs_path, entry)
        self._touch_task_updated_at(normalized_task_id)

        return {
            "ok": True,
            "task_id": normalized_task_id,
            "logs_path": str(logs_path),
            "level": safe_level,
            "written_text": text
        }

    def write_plan(self, task_id: str, text: str) -> Dict[str, Any]:
        """
        覆蓋寫入 plan.txt
        """
        normalized_task_id = self.path_manager.normalize_task_id(task_id)
        task_dir = self.path_manager.task_path(normalized_task_id)

        if not task_dir.exists() or not task_dir.is_dir():
            return {
                "ok": False,
                "error": "task_not_found",
                "task_id": normalized_task_id
            }

        plan_path = self.path_manager.task_file(normalized_task_id, "plan.txt")
        self._write_text(plan_path, text)
        self._touch_task_updated_at(normalized_task_id)

        return {
            "ok": True,
            "task_id": normalized_task_id,
            "plan_path": str(plan_path)
        }

    def read_plan(self, task_id: str) -> Dict[str, Any]:
        """
        讀取 plan.txt
        """
        normalized_task_id = self.path_manager.normalize_task_id(task_id)
        task_dir = self.path_manager.task_path(normalized_task_id)

        if not task_dir.exists() or not task_dir.is_dir():
            return {
                "ok": False,
                "error": "task_not_found",
                "task_id": normalized_task_id
            }

        plan_path = self.path_manager.task_file(normalized_task_id, "plan.txt")
        if not plan_path.exists():
            return {
                "ok": False,
                "error": "plan_not_found",
                "task_id": normalized_task_id
            }

        content = self._read_text(plan_path)
        return {
            "ok": True,
            "task_id": normalized_task_id,
            "plan_path": str(plan_path),
            "content": content
        }

    def update_task_status(self, task_id: str, status: str) -> Dict[str, Any]:
        """
        更新任務狀態
        """
        normalized_task_id = self.path_manager.normalize_task_id(task_id)
        task_dir = self.path_manager.task_path(normalized_task_id)
        task_json_path = self.path_manager.task_file(normalized_task_id, "task.json")

        if not task_dir.exists() or not task_dir.is_dir():
            return {
                "ok": False,
                "error": "task_not_found",
                "task_id": normalized_task_id
            }

        if not task_json_path.exists():
            return {
                "ok": False,
                "error": "task_json_not_found",
                "task_id": normalized_task_id
            }

        task_data = self._read_json(task_json_path)
        if not isinstance(task_data, dict):
            return {
                "ok": False,
                "error": "task_json_invalid",
                "task_id": normalized_task_id
            }

        task_data["status"] = (status or "").strip() or "unknown"
        task_data["updated_at"] = self._now_str()
        self._write_json(task_json_path, task_data)

        return {
            "ok": True,
            "task_id": normalized_task_id,
            "status": task_data["status"]
        }

    # =========================
    # Internal Helpers
    # =========================

    def _get_next_task_id(self) -> str:
        existing_numbers: List[int] = []

        if self.workspace_root.exists():
            for item in self.workspace_root.iterdir():
                if not item.is_dir():
                    continue
                match = re.match(r"^task_(\d{4})$", item.name)
                if match:
                    existing_numbers.append(int(match.group(1)))

        next_number = 1 if not existing_numbers else max(existing_numbers) + 1
        return f"task_{next_number:04d}"

    def _normalize_task_name(self, task_name: str) -> str:
        text = (task_name or "").strip()
        if text == "":
            return "untitled task"

        text = re.sub(r"\s+", " ", text)
        return text

    def _touch_task_updated_at(self, task_id: str) -> None:
        normalized_task_id = self.path_manager.normalize_task_id(task_id)
        task_json_path = self.path_manager.task_file(normalized_task_id, "task.json")

        if not task_json_path.exists():
            return

        task_data = self._read_json(task_json_path)
        if not isinstance(task_data, dict):
            return

        task_data["updated_at"] = self._now_str()
        self._write_json(task_json_path, task_data)

    def _now_str(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _write_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _append_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(text)

    def _read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def _write_json(self, path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def _read_json(self, path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None