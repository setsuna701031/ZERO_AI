from __future__ import annotations

"""Immutable evidence records produced outside Runtime and Memory."""

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from core.goals.goal_contract import clean_optional_text, clean_required_text


class EvidenceValidationState(str, Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    REJECTED = "rejected"


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    goal_id: str
    subgoal_id: str | None
    source: str
    summary: Any
    timestamp: str
    validation_state: EvidenceValidationState | str = EvidenceValidationState.PENDING
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        state = (
            self.validation_state.value
            if isinstance(self.validation_state, EvidenceValidationState)
            else str(self.validation_state or "").strip().lower()
        )
        try:
            state = EvidenceValidationState(state).value
        except ValueError as exc:
            raise ValueError("evidence_requires_valid_validation_state") from exc
        object.__setattr__(self, "evidence_id", clean_required_text(self.evidence_id, "evidence_id"))
        object.__setattr__(self, "goal_id", clean_required_text(self.goal_id, "goal_id"))
        object.__setattr__(self, "subgoal_id", clean_optional_text(self.subgoal_id))
        object.__setattr__(self, "source", clean_required_text(self.source, "evidence_source"))
        object.__setattr__(self, "summary", copy.deepcopy(self.summary))
        object.__setattr__(self, "timestamp", clean_required_text(self.timestamp, "evidence_timestamp"))
        object.__setattr__(self, "validation_state", state)
        object.__setattr__(
            self,
            "metadata",
            copy.deepcopy(dict(self.metadata)) if isinstance(self.metadata, Mapping) else {},
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvidenceRecord":
        return cls(
            evidence_id=value.get("evidence_id"),
            goal_id=value.get("goal_id"),
            subgoal_id=value.get("subgoal_id"),
            source=value.get("source"),
            summary=value.get("summary"),
            timestamp=value.get("timestamp"),
            validation_state=value.get("validation_state") or EvidenceValidationState.PENDING,
            metadata=value.get("metadata") if isinstance(value.get("metadata"), Mapping) else {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "goal_id": self.goal_id,
            "subgoal_id": self.subgoal_id,
            "source": self.source,
            "summary": copy.deepcopy(self.summary),
            "timestamp": self.timestamp,
            "validation_state": self.validation_state,
            "metadata": copy.deepcopy(dict(self.metadata)),
        }

    def __deepcopy__(self, memo: dict[int, Any]) -> "EvidenceRecord":
        return self


__all__ = ["EvidenceRecord", "EvidenceValidationState"]
