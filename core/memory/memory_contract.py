from __future__ import annotations

"""Contracts shared by the append-only engineering memory layer."""

import copy
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol, runtime_checkable


MEMORY_SCHEMA = "zero.memory.v1"


class MemoryType(str, Enum):
    TASK = "task"
    DECISION = "decision"
    ISSUE = "issue"
    ENGINEERING = "engineering"


def clean_required_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"memory_requires_{field_name}")
    return text


def clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def copy_evidence_refs(value: Any) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise TypeError("evidence_refs must be a list or tuple")
    return copy.deepcopy(list(value))


@runtime_checkable
class MemoryRecord(Protocol):
    memory_type: MemoryType

    def to_dict(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class MemoryContract:
    """Minimal envelope required for every persisted memory record."""

    memory_type: MemoryType
    record_id: str
    timestamp: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MemoryContract":
        try:
            memory_type = MemoryType(str(value.get("memory_type") or "").strip())
        except ValueError as exc:
            raise ValueError("memory_requires_valid_memory_type") from exc
        return cls(
            memory_type=memory_type,
            record_id=clean_required_text(value.get("record_id"), "record_id"),
            timestamp=clean_required_text(value.get("timestamp"), "timestamp"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MEMORY_SCHEMA,
            "memory_type": self.memory_type.value,
            "record_id": self.record_id,
            "timestamp": self.timestamp,
        }


def validate_memory_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    record = copy.deepcopy(dict(value))
    contract = MemoryContract.from_mapping(record)
    record.update(contract.to_dict())
    return record


__all__ = [
    "MEMORY_SCHEMA",
    "MemoryContract",
    "MemoryRecord",
    "MemoryType",
    "clean_optional_text",
    "clean_required_text",
    "copy_evidence_refs",
    "validate_memory_mapping",
]
