from __future__ import annotations

import copy
import hashlib
import json
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


class RuntimeRecoveryPolicyReport:
    """Read-only compatibility report for recovery policy evaluation."""

    SCHEMA = "zero.runtime.recovery_policy.compat.v1"

    def __init__(
        self,
        reasoning: Any,
        *,
        replay_trust_threshold: int = 90,
        replay_warn_threshold: int = 75,
    ) -> None:
        self.reasoning = reasoning
        self.replay_trust_threshold = int(replay_trust_threshold)
        self.replay_warn_threshold = int(replay_warn_threshold)
        payload = self._build_payload(reasoning)
        payload["fingerprint"] = _stable_policy_fingerprint(payload)
        self._payload = self._json_safe(payload)

    @property
    def payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload)

    @property
    def fingerprint(self) -> str:
        return str(self._payload.get("fingerprint") or "")

    def to_dict(self) -> dict[str, Any]:
        return self.payload

    def lineage_policy(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("lineage_policy", {}))

    def trust_threshold_policy(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("trust_threshold_policy", {}))

    def replay_policy(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("replay_policy", {}))

    def rollback_policy(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("rollback_policy", {}))

    def failed_execution_policy(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("failed_execution_policy", {}))

    def action_classification(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("action_classification", {}))

    def policy_decisions(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("policy_decisions", []))

    def _build_payload(self, reasoning: Any) -> dict[str, Any]:
        reason_payload = getattr(reasoning, "payload", {})
        if not isinstance(reason_payload, dict):
            reason_payload = {}
        lineage = reasoning.lineage_trust() if hasattr(reasoning, "lineage_trust") else {}
        replay_trust = reasoning.replay_trust() if hasattr(reasoning, "replay_trust") else {}
        replay_safety = reasoning.replay_safety() if hasattr(reasoning, "replay_safety") else {}
        rollback_candidates = (
            reasoning.rollback_candidates() if hasattr(reasoning, "rollback_candidates") else []
        )
        failed = (
            reasoning.failed_execution_recovery()
            if hasattr(reasoning, "failed_execution_recovery")
            else {}
        )
        missing_evidence = replay_trust.get("classification") == "missing_evidence"
        unsafe_lineage = lineage.get("classification") not in {"trusted", "partial"}

        lineage_policy = {
            "policy": "lineage",
            "decision": "block" if missing_evidence or unsafe_lineage else "allow",
            "reason": (
                "missing_evidence"
                if missing_evidence
                else "unsafe_lineage"
                if unsafe_lineage
                else "lineage_safe"
            ),
        }
        score = int(replay_trust.get("score", 0) or 0)
        threshold_decision = "allow"
        if missing_evidence:
            threshold_decision = "block"
        elif score < self.replay_trust_threshold:
            threshold_decision = "warn" if score >= self.replay_warn_threshold else "block"
        trust_threshold_policy = {
            "policy": "trust_threshold",
            "decision": threshold_decision,
            "score": score,
            "required_score": self.replay_trust_threshold,
        }
        replay_decision = "block" if lineage_policy["decision"] == "block" else threshold_decision
        replay_policy = {
            "policy": "replay",
            "decision": replay_decision,
            "reason": (
                "replay_allowed_with_policy_warning"
                if replay_decision == "warn"
                else "replay_blocked"
                if replay_decision == "block"
                else "replay_allowed"
            ),
            "replay_safety": replay_safety.get("classification", ""),
        }
        rollback_policy = {
            "policy": "rollback",
            "decision": "block" if replay_decision == "block" else "allow",
            "candidate_count": 0 if replay_decision == "block" else len(rollback_candidates),
            "allowed_count": 0 if replay_decision == "block" else len(rollback_candidates),
            "candidates": [
                {**copy.deepcopy(candidate), "decision": "allow", "executes_action": False}
                for candidate in rollback_candidates
                if isinstance(candidate, dict)
            ]
            if replay_decision != "block"
            else [],
        }
        failed_candidates = copy.deepcopy(failed.get("candidates", [])) if isinstance(failed, dict) else []
        failed_policy = {
            "policy": "failed_execution",
            "decision": "block" if replay_decision == "block" else "allow",
            "failed_execution_count": (
                int(failed.get("failed_execution_count", 0) or 0) if isinstance(failed, dict) else 0
            ),
            "candidate_count": 0 if replay_decision == "block" else len(failed_candidates),
            "candidates": [
                {**candidate, "decision": "allow", "executes_action": False}
                for candidate in failed_candidates
                if isinstance(candidate, dict)
            ]
            if replay_decision != "block"
            else [],
        }
        classification = "block" if replay_decision == "block" else "allow"
        decisions = [
            lineage_policy,
            trust_threshold_policy,
            replay_policy,
            rollback_policy,
            failed_policy,
        ]
        return {
            "ok": True,
            "schema": self.SCHEMA,
            "read_only": True,
            "reasoning": copy.deepcopy(reason_payload),
            "lineage_policy": lineage_policy,
            "trust_threshold_policy": trust_threshold_policy,
            "replay_policy": replay_policy,
            "rollback_policy": rollback_policy,
            "failed_execution_policy": failed_policy,
            "action_classification": {"classification": classification},
            "policy_decisions": decisions,
        }

    def _json_safe(self, payload: Any) -> dict[str, Any]:
        encoded = json.dumps(payload if isinstance(payload, dict) else {}, default=str, sort_keys=True)
        return json.loads(encoded)


class RuntimeRecoveryPolicyEvaluator:
    """Compatibility evaluator over runtime recovery reasoning."""

    def __init__(
        self,
        *,
        reasoner: Any = None,
        replay_trust_threshold: int = 90,
        replay_warn_threshold: int = 75,
    ) -> None:
        if reasoner is None:
            from core.runtime.runtime_recovery_reasoning import RuntimeRecoveryReasoner

            reasoner = RuntimeRecoveryReasoner()
        self.reasoner = reasoner
        self.replay_trust_threshold = int(replay_trust_threshold)
        self.replay_warn_threshold = int(replay_warn_threshold)

    def evaluate(self, source: Any) -> RuntimeRecoveryPolicyReport:
        return RuntimeRecoveryPolicyReport(
            self.reasoner.reason(source),
            replay_trust_threshold=self.replay_trust_threshold,
            replay_warn_threshold=self.replay_warn_threshold,
        )


def _stable_policy_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "CONTROLLED_ACTIONS",
    "HIGH_RISK_ACTIONS",
    "SAFE_RECOMMENDATION_ACTIONS",
    "RuntimeRecoveryPolicy",
    "RuntimeRecoveryPolicyDecision",
    "RuntimeRecoveryPolicyEvaluator",
    "RuntimeRecoveryPolicyReport",
]
