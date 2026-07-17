from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any


DECISION_EVIDENCE_SCHEMA = "zero.decision_evidence.v1"


@dataclass(frozen=True)
class DecisionEvidenceRecord:
    decision_id: str
    goal_id: str
    task_id: str
    source_stage: str
    observed_event: Any
    outcome_class: str
    decision: str
    decision_reason: str
    next_action: str
    evidence_refs: list[Any] = field(default_factory=list)
    created_at: float = 0.0
    confidence: Any = None
    confidence_unavailable_reason: str = ""
    links: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        record = {
            "schema": DECISION_EVIDENCE_SCHEMA,
            "decision_id": self.decision_id,
            "goal_id": self.goal_id,
            "task_id": self.task_id,
            "source_stage": self.source_stage,
            "observed_event": copy.deepcopy(self.observed_event),
            "outcome_class": self.outcome_class,
            "decision": self.decision,
            "decision_reason": self.decision_reason,
            "next_action": self.next_action,
            "evidence_refs": copy.deepcopy(self.evidence_refs),
            "created_at": self.created_at,
            "links": copy.deepcopy(self.links),
        }
        if self.confidence is not None:
            record["confidence"] = copy.deepcopy(self.confidence)
        else:
            record["confidence_unavailable_reason"] = (
                self.confidence_unavailable_reason or "confidence_not_present_in_adaptive_decision"
            )
        return record


__all__ = ["DECISION_EVIDENCE_SCHEMA", "DecisionEvidenceRecord"]

