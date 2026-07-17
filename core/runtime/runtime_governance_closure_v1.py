from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


GOVERNANCE_CLOSURE_READY = "runtime_ready"
GOVERNANCE_CLOSURE_REVIEW_REQUIRED = "runtime_review_required"
GOVERNANCE_CLOSURE_BLOCKED = "runtime_blocked"


@dataclass(frozen=True)
class RuntimeGovernanceClosure:
    closure_id: str
    replay_id: str
    seal_status: str
    closure_status: str
    continuation_allowed: bool
    review_required: bool
    blocked: bool
    reopen_protection: bool
    classification: str
    reason: str
    governance_evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "closure_id": self.closure_id,
            "replay_id": self.replay_id,
            "seal_status": self.seal_status,
            "closure_status": self.closure_status,
            "continuation_allowed": self.continuation_allowed,
            "review_required": self.review_required,
            "blocked": self.blocked,
            "reopen_protection": self.reopen_protection,
            "classification": self.classification,
            "reason": self.reason,
            "governance_evidence": dict(self.governance_evidence),
        }


class RuntimeGovernanceClosureBuilder:
    def build_closure(
        self,
        seal: Any,
    ) -> RuntimeGovernanceClosure:
        payload = (
            seal.to_dict()
            if hasattr(seal, "to_dict")
            else dict(seal)
        )

        replay_id = str(payload.get("replay_id") or "")
        seal_status = str(payload.get("seal_status") or "").lower()

        recoverable = bool(payload.get("recoverable"))
        review_required = bool(payload.get("review_required"))
        failed = bool(payload.get("failed"))

        if failed:
            closure_status = GOVERNANCE_CLOSURE_BLOCKED
            continuation_allowed = False
            blocked = True
            reopen_protection = True
            classification = "governance_failed"
            reason = "runtime_recovery_failed"
        elif review_required:
            closure_status = GOVERNANCE_CLOSURE_REVIEW_REQUIRED
            continuation_allowed = False
            blocked = False
            reopen_protection = True
            classification = "governance_review_required"
            reason = "runtime_requires_review"
        elif recoverable:
            closure_status = GOVERNANCE_CLOSURE_READY
            continuation_allowed = True
            blocked = False
            reopen_protection = True
            classification = "governance_ready"
            reason = "runtime_ready_for_continuation"
        else:
            closure_status = GOVERNANCE_CLOSURE_BLOCKED
            continuation_allowed = False
            blocked = True
            reopen_protection = True
            classification = "governance_unknown"
            reason = "runtime_governance_unresolved"

        return RuntimeGovernanceClosure(
            closure_id=f"closure::{replay_id}",
            replay_id=replay_id,
            seal_status=seal_status,
            closure_status=closure_status,
            continuation_allowed=continuation_allowed,
            review_required=review_required,
            blocked=blocked,
            reopen_protection=reopen_protection,
            classification=classification,
            reason=reason,
            governance_evidence={
                "seal_status": seal_status,
                "recoverable": recoverable,
                "review_required": review_required,
                "failed": failed,
                "source": "runtime_governance_closure_v1",
            },
        )