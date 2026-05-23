from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from core.runtime.runtime_recovery_state import (
    RECOVERY_CONTINUATION_BLOCKED,
    RECOVERY_CONTINUATION_READY,
    RECOVERY_CONTINUATION_REQUIRES_REVIEW,
    RECOVERY_CONTINUATION_REQUIRES_ROLLBACK,
    RECOVERY_CONTINUATION_UNRECOVERABLE,
)


SAFE_RECOMMENDATION_ACTIONS = {
    "attach_replay_evidence",
    "verify_recovery",
    "reconstruct_incident",
    "emit_recovery_audit",
    "recommend_continuation",
}

CONTROLLED_ACTIONS = {
    "prepare_rollback",
    "apply_state_repair",
    "execute_replay_candidate",
    "continue_runtime",
}

HIGH_RISK_ACTIONS = {
    "execute_rollback",
    "apply_rollback",
    "commit_state_repair",
    "mutate_source_state",
}


@dataclass(frozen=True)
class RuntimeRecoveryPolicyDecision:
    allowed: bool
    action_type: str
    reason: str
    requires_review: bool = False
    requires_approval: bool = False
    risk_level: str = "low"
    continuation_decision: str = RECOVERY_CONTINUATION_BLOCKED
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "action_type": self.action_type,
            "reason": self.reason,
            "requires_review": self.requires_review,
            "requires_approval": self.requires_approval,
            "risk_level": self.risk_level,
            "continuation_decision": self.continuation_decision,
            "metadata": copy.deepcopy(self.metadata),
        }


class RuntimeRecoveryPolicy:
    """Governed policy for recovery execution.

    The executor may prepare, recommend, replay references, and verify by default.
    It must not perform rollback/state mutation unless approval is explicit.
    """

    def __init__(self, *, allow_high_risk_execution: bool = False) -> None:
        self.allow_high_risk_execution = bool(allow_high_risk_execution)

    def decide_action(
        self,
        *,
        action_type: str,
        chain_status: str,
        chain_payload: dict[str, Any],
        approval: dict[str, Any] | None = None,
    ) -> RuntimeRecoveryPolicyDecision:
        action = str(action_type or "").strip()
        status = str(chain_status or "").strip().lower()
        approved = self._is_approved(approval)

        if status == "unrecoverable":
            return RuntimeRecoveryPolicyDecision(
                allowed=False,
                action_type=action,
                reason="recovery chain is unrecoverable",
                requires_review=True,
                risk_level="high",
                continuation_decision=RECOVERY_CONTINUATION_UNRECOVERABLE,
            )

        if action in HIGH_RISK_ACTIONS:
            if self.allow_high_risk_execution and approved:
                return RuntimeRecoveryPolicyDecision(
                    allowed=True,
                    action_type=action,
                    reason="high risk recovery action explicitly approved",
                    requires_approval=True,
                    risk_level="high",
                    continuation_decision=self._continuation_for_status(status),
                )
            return RuntimeRecoveryPolicyDecision(
                allowed=False,
                action_type=action,
                reason="high risk recovery action requires explicit approval",
                requires_review=True,
                requires_approval=True,
                risk_level="high",
                continuation_decision=RECOVERY_CONTINUATION_REQUIRES_REVIEW,
            )

        if status == "rollback_required" and action in {"continue_runtime", "recommend_continuation"}:
            return RuntimeRecoveryPolicyDecision(
                allowed=False,
                action_type=action,
                reason="runtime continuation is blocked until rollback is represented or approved",
                requires_review=True,
                risk_level="medium",
                continuation_decision=RECOVERY_CONTINUATION_REQUIRES_ROLLBACK,
            )

        if action in SAFE_RECOMMENDATION_ACTIONS:
            return RuntimeRecoveryPolicyDecision(
                allowed=True,
                action_type=action,
                reason="safe recovery metadata action allowed",
                risk_level="low",
                continuation_decision=self._continuation_for_status(status),
            )

        if action in CONTROLLED_ACTIONS:
            return RuntimeRecoveryPolicyDecision(
                allowed=True,
                action_type=action,
                reason="controlled recovery action allowed without source mutation",
                requires_review=status == "rollback_required",
                risk_level="medium" if status == "rollback_required" else "low",
                continuation_decision=self._continuation_for_status(status),
            )

        return RuntimeRecoveryPolicyDecision(
            allowed=False,
            action_type=action,
            reason="unknown recovery action type",
            requires_review=True,
            risk_level="medium",
            continuation_decision=RECOVERY_CONTINUATION_REQUIRES_REVIEW,
            metadata={"known_safe_actions": sorted(SAFE_RECOMMENDATION_ACTIONS)},
        )

    def decide_continuation(self, *, chain_status: str, verification_result: dict[str, Any]) -> str:
        status = str(chain_status or "").strip().lower()
        verified = bool((verification_result or {}).get("verified"))
        if status == "unrecoverable":
            return RECOVERY_CONTINUATION_UNRECOVERABLE
        if status == "rollback_required":
            return RECOVERY_CONTINUATION_REQUIRES_ROLLBACK
        if status == "verified" and verified:
            return RECOVERY_CONTINUATION_READY
        return RECOVERY_CONTINUATION_REQUIRES_REVIEW

    def _continuation_for_status(self, status: str) -> str:
        if status == "verified":
            return RECOVERY_CONTINUATION_READY
        if status == "rollback_required":
            return RECOVERY_CONTINUATION_REQUIRES_ROLLBACK
        if status == "unrecoverable":
            return RECOVERY_CONTINUATION_UNRECOVERABLE
        return RECOVERY_CONTINUATION_REQUIRES_REVIEW

    def _is_approved(self, approval: dict[str, Any] | None) -> bool:
        if not isinstance(approval, dict):
            return False
        return bool(approval.get("approved") is True or str(approval.get("status") or "").lower() == "approved")


__all__ = [
    "CONTROLLED_ACTIONS",
    "HIGH_RISK_ACTIONS",
    "SAFE_RECOMMENDATION_ACTIONS",
    "RuntimeRecoveryPolicy",
    "RuntimeRecoveryPolicyDecision",
]
