from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


class MemoryStore:
    """
    ZERO 本地記憶儲存層 v0.2

    目前功能：
    1. 寫入記憶
    2. 去重
    3. 列出全部記憶
    4. 關鍵字搜尋記憶
    5. 使用本地 JSON 檔保存
    """

    def __init__(self, file_path: str = "data/memory_store.json") -> None:
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        if not self.file_path.exists():
            self._write_data({"items": []})

    def _read_data(self) -> Dict[str, Any]:
        try:
            with self.file_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {"items": []}

        if not isinstance(data, dict):
            data = {"items": []}

        if "items" not in data or not isinstance(data["items"], list):
            data["items"] = []

        return data

    def _write_data(self, data: Dict[str, Any]) -> None:
        with self.file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _normalize_text(self, text: str) -> str:
        return " ".join((text or "").strip().lower().split())

    def write_memory(self, content: str) -> Dict[str, Any]:
        content = (content or "").strip()

        if not content:
            return {
                "ok": False,
                "error": "empty_memory_content",
                "details": ["memory content cannot be empty"],
            }

        data = self._read_data()
        items: List[Dict[str, Any]] = data["items"]

        normalized_new = self._normalize_text(content)

        for item in items:
            existing_content = str(item.get("content", "")).strip()
            if self._normalize_text(existing_content) == normalized_new:
                return {
                    "ok": True,
                    "action": "write",
                    "status": "duplicate",
                    "item": item,
                    "count": len(items),
                }

        next_id = len(items) + 1
        item = {
            "id": next_id,
            "content": content,
        }
        items.append(item)
        self._write_data(data)

        return {
            "ok": True,
            "action": "write",
            "status": "created",
            "item": item,
            "count": len(items),
        }

    def list_memories(self) -> Dict[str, Any]:
        data = self._read_data()
        items: List[Dict[str, Any]] = data["items"]

        return {
            "ok": True,
            "action": "list",
            "count": len(items),
            "items": items,
        }

    def read_memories(self) -> Dict[str, Any]:
        data = self._read_data()
        items: List[Dict[str, Any]] = data["items"]

        return {
            "ok": True,
            "action": "read",
            "count": len(items),
            "items": items,
        }

    def search_memories(self, query: str) -> Dict[str, Any]:
        query = (query or "").strip()

        if not query:
            return {
                "ok": False,
                "error": "empty_search_query",
                "details": ["search query cannot be empty"],
            }

        data = self._read_data()
        items: List[Dict[str, Any]] = data["items"]

        normalized_query = self._normalize_text(query)
        matched_items: List[Dict[str, Any]] = []

        for item in items:
            content = str(item.get("content", "")).strip()
            if normalized_query in self._normalize_text(content):
                matched_items.append(item)

        return {
            "ok": True,
            "action": "search",
            "query": query,
            "count": len(matched_items),
            "items": matched_items,
        }