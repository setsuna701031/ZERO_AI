from __future__ import annotations

"""Read-only, deterministic queries over persisted memory."""

from typing import Any

from core.memory.memory_contract import MemoryType
from core.memory.memory_repository import MemoryRepository


class MemoryQuery:
    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository

    def find_related_issues(
        self,
        task_id: str | None = None,
        *,
        status: str | None = None,
        text: str | None = None,
    ) -> list[dict[str, Any]]:
        records = self.repository.list_by_type(MemoryType.ISSUE)
        if task_id is not None:
            records = [record for record in records if record.get("related_task") == task_id]
        if status is not None:
            records = [record for record in records if record.get("status") == status]
        if text is not None:
            target = text.casefold()
            records = [
                record
                for record in records
                if target in " ".join(str(record.get(key) or "") for key in ("title", "root_cause", "fix")).casefold()
            ]
        return records

    def find_previous_decisions(
        self,
        task_id: str | None = None,
        *,
        decision: str | None = None,
        context: Any = None,
    ) -> list[dict[str, Any]]:
        records = self.repository.list_by_type(MemoryType.DECISION)
        if task_id is not None:
            records = [
                record
                for record in records
                if record.get("task_id") == task_id
                or (
                    isinstance(record.get("context"), dict)
                    and record["context"].get("task_id") == task_id
                )
            ]
        if decision is not None:
            records = [record for record in records if record.get("decision") == decision]
        if context is not None:
            records = [record for record in records if record.get("context") == context]
        return records

    def find_task_history(self, task_id: str) -> list[dict[str, Any]]:
        return [
            record
            for record in self.repository.list_by_type(MemoryType.TASK)
            if record.get("task_id") == task_id
        ]

    def find_engineering_events(
        self,
        task_id: str | None = None,
        *,
        text: str | None = None,
    ) -> list[dict[str, Any]]:
        records = self.repository.list_by_type(MemoryType.ENGINEERING)
        if task_id is not None:
            records = [record for record in records if record.get("related_task") == task_id]
        if text is None:
            return records
        target = text.casefold()
        return [
            record
            for record in records
            if target in f"{record.get('title', '')} {record.get('description', '')}".casefold()
        ]


__all__ = ["MemoryQuery"]
