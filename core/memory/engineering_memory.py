from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from core.memory.memory_contract import (
    MEMORY_SCHEMA,
    MemoryType,
    clean_optional_text,
    clean_required_text,
    copy_evidence_refs,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class EngineeringMemory:
    event_id: str
    title: str
    description: str
    evidence_refs: list[Any] = field(default_factory=list)
    timestamp: str = field(default_factory=_now)
    related_task: str | None = None
    memory_type: MemoryType = field(default=MemoryType.ENGINEERING, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", clean_required_text(self.event_id, "event_id"))
        object.__setattr__(self, "title", clean_required_text(self.title, "title"))
        object.__setattr__(self, "description", clean_required_text(self.description, "description"))
        object.__setattr__(self, "evidence_refs", copy_evidence_refs(self.evidence_refs))
        object.__setattr__(self, "timestamp", clean_required_text(self.timestamp, "timestamp"))
        object.__setattr__(self, "related_task", clean_optional_text(self.related_task))

    @property
    def record_id(self) -> str:
        return self.event_id

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EngineeringMemory":
        return cls(
            event_id=value.get("event_id") or value.get("record_id"),
            title=value.get("title"),
            description=value.get("description"),
            evidence_refs=value.get("evidence_refs") or [],
            timestamp=value.get("timestamp") or _now(),
            related_task=value.get("related_task"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MEMORY_SCHEMA,
            "memory_type": self.memory_type.value,
            "record_id": self.record_id,
            "event_id": self.event_id,
            "title": self.title,
            "description": self.description,
            "evidence_refs": copy.deepcopy(self.evidence_refs),
            "timestamp": self.timestamp,
            "related_task": self.related_task,
        }


__all__ = ["EngineeringMemory"]
