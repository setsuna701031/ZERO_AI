from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping


class AdaptiveAction(str, Enum):
    CONTINUE = "continue"
    RETRY = "retry"
    REPLAN = "replan"
    RESUME = "resume"
    BLOCK = "block"


@dataclass(frozen=True)
class DeviationReport:
    task_id: str
    step_id: str
    expected: Any
    observed: Any
    deviation_detected: bool
    reason: str
    severity: str = "none"
    recoverable: bool = True
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(asdict(self))


@dataclass(frozen=True)
class AdaptiveDecision:
    action: AdaptiveAction
    reason: str
    resume_from_step_id: str = ""
    inserted_steps: tuple[Mapping[str, Any], ...] = ()
    replaced_steps: tuple[Mapping[str, Any], ...] = ()
    requires_user_review: bool = False
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = copy.deepcopy(asdict(self))
        payload["action"] = self.action.value
        return payload


@dataclass(frozen=True)
class AdaptivePlanRevision:
    original_plan_id: str
    revised_plan_id: str
    revision_reason: str
    changed_steps: tuple[Mapping[str, Any], ...] = ()
    resume_from_step_id: str = ""
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(asdict(self))


@dataclass(frozen=True)
class AdaptiveRunResult:
    ok: bool
    status: str
    result: Mapping[str, Any]
    decision: AdaptiveDecision
    deviation: DeviationReport
    revision: AdaptivePlanRevision | None = None
    evidence_chain: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "result": copy.deepcopy(dict(self.result)),
            "decision": self.decision.to_dict(),
            "deviation": self.deviation.to_dict(),
            "revision": self.revision.to_dict() if self.revision else None,
            "evidence_chain": copy.deepcopy(list(self.evidence_chain)),
        }


__all__ = [
    "AdaptiveAction",
    "AdaptiveDecision",
    "AdaptivePlanRevision",
    "AdaptiveRunResult",
    "DeviationReport",
]
