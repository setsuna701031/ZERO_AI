from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from core.memory.memory_contract import (
    MEMORY_SCHEMA,
    MemoryType,
    clean_required_text,
    copy_evidence_refs,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class DecisionMemory:
    decision_id: str
    context: Any
    decision: str
    reason: str
    evidence_refs: list[Any] = field(default_factory=list)
    timestamp: str = field(default_factory=_now)
    memory_type: MemoryType = field(default=MemoryType.DECISION, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", clean_required_text(self.decision_id, "decision_id"))
        object.__setattr__(self, "decision", clean_required_text(self.decision, "decision"))
        object.__setattr__(self, "reason", clean_required_text(self.reason, "reason"))
        object.__setattr__(self, "context", copy.deepcopy(self.context))
        object.__setattr__(self, "evidence_refs", copy_evidence_refs(self.evidence_refs))
        object.__setattr__(self, "timestamp", clean_required_text(self.timestamp, "timestamp"))

    @property
    def record_id(self) -> str:
        return self.decision_id

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "DecisionMemory":
        return cls(
            decision_id=value.get("decision_id") or value.get("record_id"),
            context=value.get("context"),
            decision=value.get("decision"),
            reason=value.get("reason"),
            evidence_refs=value.get("evidence_refs") or [],
            timestamp=value.get("timestamp") or _now(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MEMORY_SCHEMA,
            "memory_type": self.memory_type.value,
            "record_id": self.record_id,
            "decision_id": self.decision_id,
            "context": copy.deepcopy(self.context),
            "decision": self.decision,
            "reason": self.reason,
            "evidence_refs": copy.deepcopy(self.evidence_refs),
            "timestamp": self.timestamp,
        }


__all__ = ["DecisionMemory"]
