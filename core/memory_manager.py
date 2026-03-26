from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _safe_lower_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.lower()
    try:
        return json.dumps(value, ensure_ascii=False).lower()
    except Exception:
        return str(value).lower()


@dataclass
class MemoryRecord:
    id: str
    memory_type: str
    root_task_id: Optional[str]
    task_id: Optional[str]
    content: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MemoryManager:
    """
    簡單 JSON Memory Store

    目前提供：
    - task_session_start
    - task_step_completed
    - task_step_failed
    - task_summary
    - recent / search / clear
    - 給 planner 使用的查詢介面

    兼容：
    - 舊版 memory_store.json
    - 壞掉或混入字串項目的舊資料
    """

    def __init__(self, storage_path: str = "data/memory_store.json") -> None:
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._records: List[MemoryRecord] = []
        self._load()

    # -------------------------------------------------------------------------
    # 基礎持久化
    # -------------------------------------------------------------------------
    def _load(self) -> None:
        if not self.storage_path.exists():
            self._records = []
            self._save()
            return

        try:
            raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception:
            raw = []

        # 舊資料若不是 list，直接當空
        if not isinstance(raw, list):
            raw = []

        records: List[MemoryRecord] = []

        for index, item in enumerate(raw, start=1):
            normalized = self._normalize_raw_record(item=item, index=index)
            if normalized is None:
                continue
            records.append(normalized)

        self._records = records
        self._save()

    def _normalize_raw_record(self, item: Any, index: int) -> Optional[MemoryRecord]:
        """
        兼容舊格式 / 壞資料：
        - dict: 正常解析
        - str / int / list / 其他: 包成 legacy_unknown record
        """
        if isinstance(item, dict):
            record_id = str(item.get("id") or f"mem_{index:06d}")
            memory_type = str(item.get("memory_type") or "legacy_unknown")
            root_task_id = item.get("root_task_id")
            task_id = item.get("task_id")

            raw_content = item.get("content", {})
            if isinstance(raw_content, dict):
                content = dict(raw_content)
            else:
                content = {"raw_content": raw_content}

            created_at = str(item.get("created_at") or _utc_now_iso())

            return MemoryRecord(
                id=record_id,
                memory_type=memory_type,
                root_task_id=root_task_id,
                task_id=task_id,
                content=content,
                created_at=created_at,
            )

        if item is None:
            return None

        return MemoryRecord(
            id=f"mem_{index:06d}",
            memory_type="legacy_unknown",
            root_task_id=None,
            task_id=None,
            content={"raw_legacy_item": item},
            created_at=_utc_now_iso(),
        )

    def _save(self) -> None:
        data = [record.to_dict() for record in self._records]
        self.storage_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _append_record(
        self,
        memory_type: str,
        root_task_id: Optional[str],
        task_id: Optional[str],
        content: Dict[str, Any],
    ) -> None:
        record = MemoryRecord(
            id=f"mem_{len(self._records) + 1:06d}",
            memory_type=memory_type,
            root_task_id=root_task_id,
            task_id=task_id,
            content=content,
        )
        self._records.append(record)
        self._save()

    # -------------------------------------------------------------------------
    # 對外查詢
    # -------------------------------------------------------------------------
    def get_all_records(self) -> List[Dict[str, Any]]:
        return [item.to_dict() for item in self._records]

    def get_recent_records(self, limit: int = 20) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        return [item.to_dict() for item in self._records[-limit:]]

    def get_records_by_root_task(self, root_task_id: str) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for item in self._records:
            if item.root_task_id == root_task_id:
                result.append(item.to_dict())
        return result

    def get_records_by_type(self, memory_type: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        result = [item.to_dict() for item in self._records if item.memory_type == memory_type]
        if limit is not None and limit > 0:
            return result[-limit:]
        return result

    def search_text(self, keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
        keyword = (keyword or "").strip().lower()
        if not keyword:
            return []

        matched: List[Dict[str, Any]] = []
        for item in self._records:
            haystack = " ".join(
                [
                    _safe_lower_text(item.memory_type),
                    _safe_lower_text(item.root_task_id),
                    _safe_lower_text(item.task_id),
                    _safe_lower_text(item.content),
                ]
            )
            if keyword in haystack:
                matched.append(item.to_dict())

        if limit <= 0:
            return matched
        return matched[-limit:]

    def clear(self) -> None:
        self._records = []
        self._save()

    # -------------------------------------------------------------------------
    # 給 planner / agent 使用的高階查詢
    # -------------------------------------------------------------------------
    def find_similar_goal_records(self, goal: str, limit: int = 20) -> List[Dict[str, Any]]:
        keyword = (goal or "").strip().lower()
        if not keyword:
            return []

        matches: List[Dict[str, Any]] = []
        for item in self._records:
            content = item.content or {}
            goal_text = _safe_lower_text(content.get("goal"))
            if keyword in goal_text:
                matches.append(item.to_dict())

        if limit <= 0:
            return matches
        return matches[-limit:]

    def get_lessons_for_goal(self, goal: str, limit: int = 20) -> List[str]:
        results: List[str] = []
        for item in self.find_similar_goal_records(goal=goal, limit=limit):
            content = item.get("content", {}) or {}
            summary = content.get("summary", {}) or {}
            lessons = summary.get("lessons", []) or content.get("lessons", []) or []
            for lesson in lessons:
                lesson_text = str(lesson).strip()
                if lesson_text:
                    results.append(lesson_text)
        return results[-limit:]

    def get_successful_step_titles(self, goal: str, limit: int = 20) -> List[str]:
        titles: List[str] = []
        for item in self.find_similar_goal_records(goal=goal, limit=limit):
            content = item.get("content", {}) or {}
            summary = content.get("summary", {}) or {}
            completed_steps = summary.get("completed_steps", []) or content.get("completed_steps", []) or []
            for step in completed_steps:
                title = str(step.get("task_title", "")).strip()
                if title:
                    titles.append(title)
        return titles[-limit:]

    def get_failed_notes(self, goal: str, limit: int = 20) -> List[str]:
        notes: List[str] = []
        for item in self.find_similar_goal_records(goal=goal, limit=limit):
            content = item.get("content", {}) or {}
            summary = content.get("summary", {}) or {}
            failed_steps = summary.get("failed_steps", []) or content.get("failed_steps", []) or []
            for step in failed_steps:
                title = str(step.get("task_title", "")).strip()
                error = str(step.get("error", "")).strip()
                retry_count = step.get("retry_count", 0)
                reflection_count = step.get("reflection_count", 0)

                parts = []
                if title:
                    parts.append(f"title={title}")
                if error:
                    parts.append(f"error={error}")
                parts.append(f"retry={retry_count}")
                parts.append(f"reflection={reflection_count}")

                notes.append(", ".join(parts))
        return notes[-limit:]

    # -------------------------------------------------------------------------
    # Agent 記錄方法
    # -------------------------------------------------------------------------
    def record_task_started(
        self,
        root_task_id: str,
        goal: str,
        subtasks: List[str],
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._append_record(
            memory_type="task_session_start",
            root_task_id=root_task_id,
            task_id=root_task_id,
            content={
                "goal": goal,
                "subtasks": list(subtasks),
                "context": context or {},
                "status": "started",
            },
        )

    def record_step_completed(
        self,
        root_task_id: str,
        task_id: str,
        task_title: str,
        result: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._append_record(
            memory_type="task_step_completed",
            root_task_id=root_task_id,
            task_id=task_id,
            content={
                "task_title": task_title,
                "result": result,
                "success": True,
                "meta": meta or {},
            },
        )

    def record_step_failed(
        self,
        root_task_id: str,
        task_id: str,
        task_title: str,
        error: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._append_record(
            memory_type="task_step_failed",
            root_task_id=root_task_id,
            task_id=task_id,
            content={
                "task_title": task_title,
                "error": error,
                "success": False,
                "meta": meta or {},
            },
        )

    def record_task_completed_summary(
        self,
        root_task_id: str,
        goal: str,
        completed_steps: List[Dict[str, Any]],
        failed_steps: List[Dict[str, Any]],
        final_status: str,
        extra_summary: Optional[Dict[str, Any]] = None,
    ) -> None:
        content: Dict[str, Any] = {
            "goal": goal,
            "final_status": final_status,
            "completed_steps": completed_steps,
            "failed_steps": failed_steps,
        }

        if extra_summary:
            content["summary"] = extra_summary
            if extra_summary.get("lessons"):
                content["lessons"] = list(extra_summary.get("lessons", []))

        self._append_record(
            memory_type="task_summary",
            root_task_id=root_task_id,
            task_id=root_task_id,
            content=content,
        )