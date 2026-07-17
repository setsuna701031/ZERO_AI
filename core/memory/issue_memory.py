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
class IssueMemory:
    issue_id: str
    title: str
    root_cause: str
    fix: str
    related_task: str | None
    evidence_refs: list[Any] = field(default_factory=list)
    status: str = "open"
    timestamp: str = field(default_factory=_now)
    memory_type: MemoryType = field(default=MemoryType.ISSUE, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "issue_id", clean_required_text(self.issue_id, "issue_id"))
        object.__setattr__(self, "title", clean_required_text(self.title, "title"))
        object.__setattr__(self, "root_cause", clean_required_text(self.root_cause, "root_cause"))
        object.__setattr__(self, "fix", clean_required_text(self.fix, "fix"))
        object.__setattr__(self, "related_task", clean_optional_text(self.related_task))
        object.__setattr__(self, "evidence_refs", copy_evidence_refs(self.evidence_refs))
        object.__setattr__(self, "status", clean_required_text(self.status, "status"))
        object.__setattr__(self, "timestamp", clean_required_text(self.timestamp, "timestamp"))

    @property
    def record_id(self) -> str:
        return self.issue_id

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "IssueMemory":
        return cls(
            issue_id=value.get("issue_id") or value.get("record_id"),
            title=value.get("title"),
            root_cause=value.get("root_cause"),
            fix=value.get("fix"),
            related_task=value.get("related_task"),
            evidence_refs=value.get("evidence_refs") or [],
            status=value.get("status") or "open",
            timestamp=value.get("timestamp") or _now(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MEMORY_SCHEMA,
            "memory_type": self.memory_type.value,
            "record_id": self.record_id,
            "issue_id": self.issue_id,
            "title": self.title,
            "root_cause": self.root_cause,
            "fix": self.fix,
            "related_task": self.related_task,
            "evidence_refs": copy.deepcopy(self.evidence_refs),
            "status": self.status,
            "timestamp": self.timestamp,
        }


__all__ = ["IssueMemory"]
