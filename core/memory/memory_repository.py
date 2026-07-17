from __future__ import annotations

"""Append-only JSONL persistence for engineering memory records."""

import copy
import json
from pathlib import Path
from typing import Any, Mapping

from core.memory.memory_contract import MemoryRecord, MemoryType, validate_memory_mapping


class MemoryRepository:
    def __init__(self, repo_root: str | Path, *, storage_path: str | Path | None = None) -> None:
        self.repo_root = Path(repo_root)
        self.storage_path = Path(storage_path) if storage_path is not None else Path("runtime/memory/memory.jsonl")
        if not self.storage_path.is_absolute():
            self.storage_path = self.repo_root / self.storage_path

    def append(self, memory: MemoryRecord | Mapping[str, Any]) -> dict[str, Any]:
        if isinstance(memory, Mapping):
            raw = dict(memory)
        elif isinstance(memory, MemoryRecord):
            raw = memory.to_dict()
        else:
            raise TypeError("memory must implement MemoryRecord or be a mapping")
        record = validate_memory_mapping(raw)
        try:
            encoded = json.dumps(record, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("memory_record_must_be_json_serializable") from exc
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self.storage_path.open("a", encoding="utf-8") as stream:
            stream.write(encoded + "\n")
        return copy.deepcopy(record)

    def query(
        self,
        criteria: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        expected = dict(criteria or {})
        expected.update(filters)
        return [
            record
            for record in self._load_records()
            if all(record.get(key) == value for key, value in expected.items())
        ]

    def list_by_type(self, memory_type: MemoryType | str) -> list[dict[str, Any]]:
        value = memory_type.value if isinstance(memory_type, MemoryType) else str(memory_type).strip()
        return self.query(memory_type=value)

    def list_by_task(self, task_id: str) -> list[dict[str, Any]]:
        target = str(task_id or "").strip()
        return [
            record
            for record in self._load_records()
            if record.get("task_id") == target or record.get("related_task") == target
        ]

    def list_recent(
        self,
        limit: int = 10,
        *,
        memory_type: MemoryType | str | None = None,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        records = self._load_records()
        if memory_type is not None:
            value = memory_type.value if isinstance(memory_type, MemoryType) else str(memory_type).strip()
            records = [record for record in records if record.get("memory_type") == value]
        return sorted(
            records,
            key=lambda record: str(record.get("timestamp") or ""),
            reverse=True,
        )[:limit]

    def _load_records(self) -> list[dict[str, Any]]:
        if not self.storage_path.is_file():
            return []
        records: list[dict[str, Any]] = []
        with self.storage_path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    value = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid_memory_jsonl_line:{line_number}") from exc
                if not isinstance(value, Mapping):
                    raise ValueError(f"invalid_memory_record_line:{line_number}")
                records.append(validate_memory_mapping(value))
        return records


__all__ = ["MemoryRepository"]
