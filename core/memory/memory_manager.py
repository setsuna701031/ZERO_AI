from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class MemoryManager:
    """
    ZERO Memory Manager (lessons v1)

    先做最小工程記憶：
    - 只存 task lessons
    - JSONL append-only
    - 可取 recent lessons
    - 可依 goal / task_type 做簡單 relevant retrieval

    不做：
    - 向量資料庫
    - embedding
    - 複雜人格記憶
    """

    def __init__(
        self,
        workspace_root: Path | str,
        memory_dir_name: str = "_memory",
        lesson_file_name: str = "lessons.jsonl",
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.memory_dir = self.workspace_root / memory_dir_name
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        self.lesson_file = self.memory_dir / lesson_file_name
        if not self.lesson_file.exists():
            self.lesson_file.touch()

    # =========================================================
    # Public API
    # =========================================================

    def save_lesson(self, lesson: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(lesson, dict):
            raise TypeError("lesson must be a dict.")

        normalized = self._normalize_lesson(lesson)

        with open(self.lesson_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(normalized, ensure_ascii=False) + "\n")

        return {
            "success": True,
            "summary": "Lesson saved.",
            "data": {
                "lesson_file": str(self.lesson_file),
                "lesson_id": normalized["lesson_id"],
            },
            "error": None,
        }

    def get_recent_lessons(self, limit: int = 5) -> List[Dict[str, Any]]:
        lessons = self._load_all_lessons()
        if limit <= 0:
            return []
        return lessons[-limit:]

    def get_relevant_lessons(
        self,
        goal: str,
        task_type: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        goal_text = str(goal or "").strip()
        if not goal_text:
            return self.get_recent_lessons(limit=limit)

        query_tokens = self._tokenize(goal_text)
        lessons = self._load_all_lessons()

        scored: List[Tuple[int, Dict[str, Any]]] = []
        for lesson in lessons:
            score = self._score_lesson(
                lesson=lesson,
                query_tokens=query_tokens,
                task_type=task_type,
            )
            if score > 0:
                scored.append((score, lesson))

        scored.sort(key=lambda item: (item[0], item[1].get("created_at", "")), reverse=True)

        top = [item[1] for item in scored[: max(limit, 0)]]
        if top:
            return top

        return self.get_recent_lessons(limit=limit)

    def get_memory_summary(self) -> Dict[str, Any]:
        lessons = self._load_all_lessons()
        success_count = 0
        failure_count = 0

        for lesson in lessons:
            outcome = str(lesson.get("outcome", "")).strip().lower()
            if outcome == "success":
                success_count += 1
            elif outcome == "failure":
                failure_count += 1

        return {
            "lesson_count": len(lessons),
            "success_count": success_count,
            "failure_count": failure_count,
            "lesson_file": str(self.lesson_file),
        }

    # =========================================================
    # Internal
    # =========================================================

    def _load_all_lessons(self) -> List[Dict[str, Any]]:
        lessons: List[Dict[str, Any]] = []

        if not self.lesson_file.exists():
            return lessons

        with open(self.lesson_file, "r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw:
                    continue

                try:
                    item = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if isinstance(item, dict):
                    lessons.append(item)

        return lessons

    def _normalize_lesson(self, lesson: Dict[str, Any]) -> Dict[str, Any]:
        created_at = str(
            lesson.get("created_at")
            or datetime.now(timezone.utc).isoformat()
        ).strip()

        goal = str(lesson.get("goal", "")).strip()
        task_type = str(lesson.get("task_type", "general")).strip() or "general"
        outcome = str(lesson.get("outcome", "unknown")).strip().lower() or "unknown"

        what_worked = lesson.get("what_worked", [])
        if not isinstance(what_worked, list):
            what_worked = [str(what_worked)]

        what_failed = lesson.get("what_failed", [])
        if not isinstance(what_failed, list):
            what_failed = [str(what_failed)]

        suggested_next_time = lesson.get("suggested_next_time", [])
        if not isinstance(suggested_next_time, list):
            suggested_next_time = [str(suggested_next_time)]

        tools_used = lesson.get("tools_used", [])
        if not isinstance(tools_used, list):
            tools_used = [str(tools_used)]

        tags = lesson.get("tags", [])
        if not isinstance(tags, list):
            tags = [str(tags)]

        goal_summary = str(lesson.get("goal_summary", goal[:120])).strip()
        error = lesson.get("error")
        task_name = str(lesson.get("task_name", "")).strip()

        lesson_id = str(lesson.get("lesson_id", "")).strip()
        if not lesson_id:
            stamp = created_at.replace(":", "").replace("-", "").replace(".", "")
            safe_task_name = task_name or "task"
            lesson_id = f"{safe_task_name}_{stamp}"

        normalized = {
            "lesson_id": lesson_id,
            "created_at": created_at,
            "task_name": task_name,
            "goal": goal,
            "goal_summary": goal_summary,
            "task_type": task_type,
            "outcome": outcome,
            "what_worked": [str(x).strip() for x in what_worked if str(x).strip()],
            "what_failed": [str(x).strip() for x in what_failed if str(x).strip()],
            "suggested_next_time": [
                str(x).strip() for x in suggested_next_time if str(x).strip()
            ],
            "tools_used": [str(x).strip() for x in tools_used if str(x).strip()],
            "tags": [str(x).strip() for x in tags if str(x).strip()],
            "error": None if error is None else str(error).strip(),
        }
        return normalized

    def _score_lesson(
        self,
        lesson: Dict[str, Any],
        query_tokens: List[str],
        task_type: Optional[str],
    ) -> int:
        score = 0

        lesson_task_type = str(lesson.get("task_type", "")).strip().lower()
        if task_type and lesson_task_type == str(task_type).strip().lower():
            score += 5

        searchable_parts = [
            str(lesson.get("goal", "")),
            str(lesson.get("goal_summary", "")),
            " ".join(str(x) for x in lesson.get("what_worked", [])),
            " ".join(str(x) for x in lesson.get("what_failed", [])),
            " ".join(str(x) for x in lesson.get("suggested_next_time", [])),
            " ".join(str(x) for x in lesson.get("tools_used", [])),
            " ".join(str(x) for x in lesson.get("tags", [])),
        ]
        searchable_text = " ".join(searchable_parts).lower()

        for token in query_tokens:
            if token in searchable_text:
                score += 2

        if lesson.get("outcome") == "failure":
            score += 1

        if lesson.get("outcome") == "success":
            score += 1

        return score

    def _tokenize(self, text: str) -> List[str]:
        raw_tokens = re.findall(r"[a-zA-Z0-9_\-\u4e00-\u9fff]+", text.lower())
        seen = set()
        tokens: List[str] = []

        for token in raw_tokens:
            clean = token.strip()
            if len(clean) < 2:
                continue
            if clean in seen:
                continue
            seen.add(clean)
            tokens.append(clean)

        return tokens