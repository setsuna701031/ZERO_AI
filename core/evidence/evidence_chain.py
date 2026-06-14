from __future__ import annotations

"""Read-only validation summary for evidence associated with a goal."""

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from core.evidence.evidence_record import EvidenceRecord
from core.evidence.evidence_validator import is_provenance_validated_evidence
from core.goals.goal_contract import clean_optional_text, clean_required_text, copy_text_list


@dataclass(frozen=True)
class EvidenceChain:
    goal_id: str
    subgoal_id: str | None
    evidence_ids: list[str] = field(default_factory=list)
    validated_evidence_ids: list[str] = field(default_factory=list)
    validation_summary: Mapping[str, int] = field(default_factory=dict)
    has_validated_evidence: bool = False
    rejected_count: int = 0
    pending_count: int = 0
    evidence_sources: Mapping[str, int] = field(default_factory=dict)
    validated_evidence_refs: list[EvidenceRecord] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        summary_source = self.validation_summary if isinstance(self.validation_summary, Mapping) else {}
        summary = {
            "validated": int(summary_source.get("validated", 0)),
            "rejected": int(summary_source.get("rejected", self.rejected_count)),
            "pending": int(summary_source.get("pending", self.pending_count)),
        }
        source_summary = self.evidence_sources if isinstance(self.evidence_sources, Mapping) else {}
        object.__setattr__(self, "goal_id", clean_required_text(self.goal_id, "goal_id"))
        object.__setattr__(self, "subgoal_id", clean_optional_text(self.subgoal_id))
        object.__setattr__(self, "evidence_ids", copy_text_list(self.evidence_ids, "evidence_ids"))
        object.__setattr__(
            self,
            "validated_evidence_ids",
            copy_text_list(self.validated_evidence_ids, "validated_evidence_ids"),
        )
        object.__setattr__(self, "validation_summary", summary)
        object.__setattr__(self, "has_validated_evidence", summary["validated"] > 0)
        object.__setattr__(self, "rejected_count", summary["rejected"])
        object.__setattr__(self, "pending_count", summary["pending"])
        object.__setattr__(
            self,
            "evidence_sources",
            {str(key): int(value) for key, value in source_summary.items() if str(key).strip()},
        )
        object.__setattr__(self, "validated_evidence_refs", list(self.validated_evidence_refs))

    @classmethod
    def from_records(
        cls,
        goal_id: str,
        records: Sequence[EvidenceRecord | Mapping[str, Any]],
        *,
        subgoal_id: str | None = None,
    ) -> "EvidenceChain":
        target_goal = clean_required_text(goal_id, "goal_id")
        target_subgoal = clean_optional_text(subgoal_id)
        selected: list[EvidenceRecord] = []
        for value in records:
            record = value if isinstance(value, EvidenceRecord) else EvidenceRecord.from_mapping(value)
            if record.goal_id == target_goal and (target_subgoal is None or record.subgoal_id == target_subgoal):
                selected.append(record)
        validated = [record for record in selected if is_provenance_validated_evidence(record, goal_id=target_goal)]
        counts = {
            "validated": len(validated),
            "rejected": sum(record.validation_state == "rejected" for record in selected),
            "pending": sum(record.validation_state == "pending" for record in selected),
        }
        sources: dict[str, int] = {}
        for record in selected:
            source = str(record.source or "unknown").strip() or "unknown"
            sources[source] = sources.get(source, 0) + 1
        return cls(
            goal_id=target_goal,
            subgoal_id=target_subgoal,
            evidence_ids=[record.evidence_id for record in selected],
            validated_evidence_ids=[record.evidence_id for record in validated],
            validation_summary=counts,
            evidence_sources=sources,
            validated_evidence_refs=validated,
        )

    @classmethod
    def from_summary(cls, summary: Mapping[str, Any]) -> "EvidenceChain":
        return cls(
            goal_id=summary.get("goal_id"),
            subgoal_id=summary.get("subgoal_id"),
            evidence_ids=summary.get("evidence_ids") or [],
            validation_summary={
                "validated": 0,
                "rejected": int(summary.get("rejected_count") or 0),
                "pending": int(summary.get("pending_count") or 0),
            },
            evidence_sources=summary.get("evidence_sources") or {},
        )

    @property
    def validated_count(self) -> int:
        return int(self.validation_summary.get("validated", 0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "subgoal_id": self.subgoal_id,
            "evidence_ids": copy.deepcopy(self.evidence_ids),
            "validated_evidence_ids": copy.deepcopy(self.validated_evidence_ids),
            "validation_summary": copy.deepcopy(dict(self.validation_summary)),
            "has_validated_evidence": self.has_validated_evidence,
            "validated_count": self.validated_count,
            "rejected_count": self.rejected_count,
            "pending_count": self.pending_count,
            "evidence_sources": copy.deepcopy(dict(self.evidence_sources)),
        }


__all__ = ["EvidenceChain"]
