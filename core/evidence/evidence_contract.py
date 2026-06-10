from __future__ import annotations

"""Collection request emitted by AdaptiveDispatcher instead of Runtime work."""

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.goals.goal_contract import clean_optional_text, clean_required_text, copy_evidence_refs


@dataclass(frozen=True)
class EvidenceContract:
    plan_id: str
    goal_id: str
    subgoal_id: str | None
    reason: str
    evidence_required: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", clean_required_text(self.plan_id, "evidence_plan_id"))
        object.__setattr__(self, "goal_id", clean_required_text(self.goal_id, "goal_id"))
        object.__setattr__(self, "subgoal_id", clean_optional_text(self.subgoal_id))
        object.__setattr__(self, "reason", clean_required_text(self.reason, "evidence_contract_reason"))
        object.__setattr__(self, "evidence_required", copy_evidence_refs(self.evidence_required))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvidenceContract":
        return cls(
            plan_id=value.get("plan_id"),
            goal_id=value.get("goal_id"),
            subgoal_id=value.get("subgoal_id"),
            reason=value.get("reason"),
            evidence_required=value.get("evidence_required") or [],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal_id": self.goal_id,
            "subgoal_id": self.subgoal_id,
            "reason": self.reason,
            "evidence_required": copy.deepcopy(self.evidence_required),
        }


__all__ = ["EvidenceContract"]
