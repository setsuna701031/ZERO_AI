from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.runtime.runtime_recovery_reasoning import (
    RuntimeRecoveryReasoner,
    RuntimeRecoveryReasoningReport,
)


POLICY_ALLOW = "allow"
POLICY_WARN = "warn"
POLICY_BLOCK = "block"


class RuntimeRecoveryPolicyReport:
    SCHEMA = "zero.runtime.recovery_policy.v1"

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = self._json_safe(payload)

    @property
    def payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload)

    @property
    def fingerprint(self) -> str:
        return str(self._payload.get("fingerprint") or "")

    def replay_policy(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("replay_policy", {}))

    def rollback_policy(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("rollback_policy", {}))

    def failed_execution_policy(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("failed_execution_policy", {}))

    def lineage_policy(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("lineage_policy", {}))

    def trust_threshold_policy(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("trust_threshold_policy", {}))

    def action_classification(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("action_classification", {}))

    def policy_decisions(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("policy_decisions", []))

    def _json_safe(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            payload = {}
        encoded = json.dumps(
            payload,
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return json.loads(encoded)


class RuntimeRecoveryPolicyEvaluator:
    """Read-only policy classification over recovery reasoning results."""

    def __init__(
        self,
        *,
        reasoner: RuntimeRecoveryReasoner | None = None,
        replay_trust_threshold: int = 90,
        replay_warn_threshold: int = 70,
    ) -> None:
        self.reasoner = reasoner if reasoner is not None else RuntimeRecoveryReasoner()
        self.replay_trust_threshold = int(replay_trust_threshold)
        self.replay_warn_threshold = int(replay_warn_threshold)

    def evaluate(self, source: Any) -> RuntimeRecoveryPolicyReport:
        reasoning = self._reasoning_report(source)
        reasoning_payload = reasoning.payload
        lineage_policy = self.evaluate_lineage_policy(reasoning)
        trust_threshold_policy = self.evaluate_replay_trust_threshold(reasoning)
        replay_policy = self.evaluate_replay_policy(
            reasoning,
            lineage_policy=lineage_policy,
            trust_threshold_policy=trust_threshold_policy,
        )
        rollback_policy = self.evaluate_rollback_policy(
            reasoning,
            replay_policy=replay_policy,
        )
        failed_execution_policy = self.evaluate_failed_execution_policy(
            reasoning,
            replay_policy=replay_policy,
        )
        policy_decisions = self._policy_decisions_from(
            replay_policy,
            rollback_policy,
            failed_execution_policy,
        )
        action_classification = self.classify_recovery_actions(
            policy_decisions,
            replay_policy=replay_policy,
        )
        payload = {
            "ok": True,
            "schema": RuntimeRecoveryPolicyReport.SCHEMA,
            "mode": "policy_classification_only",
            "read_only": True,
            "executes_recovery": False,
            "executes_rollback": False,
            "executes_repair": False,
            "source": {
                "reasoning_fingerprint": reasoning.fingerprint,
                "replay_fingerprint": self._safe_text(
                    self._safe_mapping(reasoning_payload.get("source")).get("replay_fingerprint")
                ),
            },
            "policy_config": {
                "replay_trust_threshold": self.replay_trust_threshold,
                "replay_warn_threshold": self.replay_warn_threshold,
            },
            "lineage_policy": lineage_policy,
            "trust_threshold_policy": trust_threshold_policy,
            "replay_policy": replay_policy,
            "rollback_policy": rollback_policy,
            "failed_execution_policy": failed_execution_policy,
            "policy_decisions": policy_decisions,
            "action_classification": action_classification,
        }
        payload["fingerprint"] = self._fingerprint(payload)
        return RuntimeRecoveryPolicyReport(payload)

    def evaluate_lineage_policy(self, source: Any) -> dict[str, Any]:
        reasoning = self._reasoning_report(source)
        lineage = reasoning.lineage_trust()
        classification = self._safe_text(lineage.get("classification"))
        decision = POLICY_BLOCK
        reason = "unsafe_lineage"
        if classification == "trusted":
            decision = POLICY_ALLOW
            reason = "trusted_lineage"
        elif classification == "partial":
            decision = POLICY_WARN
            reason = "partial_lineage"
        result = {
            "policy": "lineage_trust",
            "decision": decision,
            "reason": reason,
            "lineage_classification": classification,
            "trusted": bool(lineage.get("trusted", False)),
            "action": "none",
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def evaluate_replay_trust_threshold(self, source: Any) -> dict[str, Any]:
        reasoning = self._reasoning_report(source)
        replay_trust = reasoning.replay_trust()
        score = self._safe_int(replay_trust.get("score"), 0)
        decision = POLICY_BLOCK
        reason = "replay_trust_below_threshold"
        if score >= self.replay_trust_threshold:
            decision = POLICY_ALLOW
            reason = "replay_trust_threshold_met"
        elif score >= self.replay_warn_threshold:
            decision = POLICY_WARN
            reason = "replay_trust_warning_threshold_met"
        result = {
            "policy": "replay_trust_threshold",
            "decision": decision,
            "reason": reason,
            "score": score,
            "required_score": self.replay_trust_threshold,
            "warn_score": self.replay_warn_threshold,
            "classification": self._safe_text(replay_trust.get("classification")),
            "action": "none",
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def evaluate_replay_policy(
        self,
        source: Any,
        *,
        lineage_policy: dict[str, Any] | None = None,
        trust_threshold_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reasoning = self._reasoning_report(source)
        replay_safety = reasoning.replay_safety()
        lineage_policy = (
            self._safe_mapping(lineage_policy)
            if lineage_policy is not None
            else self.evaluate_lineage_policy(reasoning)
        )
        trust_threshold_policy = (
            self._safe_mapping(trust_threshold_policy)
            if trust_threshold_policy is not None
            else self.evaluate_replay_trust_threshold(reasoning)
        )

        decision = POLICY_BLOCK
        reason = "replay_policy_blocked"
        if not bool(replay_safety.get("safe", False)):
            reason = self._safe_text(replay_safety.get("classification")) or reason
        elif lineage_policy.get("decision") == POLICY_BLOCK:
            reason = "unsafe_lineage"
        elif trust_threshold_policy.get("decision") == POLICY_BLOCK:
            reason = "replay_trust_threshold_not_met"
        elif lineage_policy.get("decision") == POLICY_WARN or trust_threshold_policy.get("decision") == POLICY_WARN:
            decision = POLICY_WARN
            reason = "replay_allowed_with_policy_warning"
        else:
            decision = POLICY_ALLOW
            reason = "replay_policy_allowed"

        result = {
            "policy": "replay",
            "decision": decision,
            "reason": reason,
            "safe": bool(replay_safety.get("safe", False)),
            "replay_safety_classification": self._safe_text(replay_safety.get("classification")),
            "lineage_decision": self._safe_text(lineage_policy.get("decision")),
            "trust_threshold_decision": self._safe_text(trust_threshold_policy.get("decision")),
            "action": "none",
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def evaluate_rollback_policy(
        self,
        source: Any,
        *,
        replay_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reasoning = self._reasoning_report(source)
        replay_policy = (
            self._safe_mapping(replay_policy)
            if replay_policy is not None
            else self.evaluate_replay_policy(reasoning)
        )
        candidates = reasoning.rollback_candidates()
        policy_candidates = [
            self._classify_candidate(
                candidate,
                default_action_type="rollback",
                replay_policy=replay_policy,
            )
            for candidate in candidates
            if isinstance(candidate, dict)
        ]
        allowed = [
            candidate
            for candidate in policy_candidates
            if candidate.get("decision") == POLICY_ALLOW
        ]
        warned = [
            candidate
            for candidate in policy_candidates
            if candidate.get("decision") == POLICY_WARN
        ]

        decision = POLICY_BLOCK
        reason = "no_rollback_candidates"
        if replay_policy.get("decision") == POLICY_BLOCK:
            reason = "replay_policy_blocks_rollback"
        elif allowed and replay_policy.get("decision") == POLICY_ALLOW:
            decision = POLICY_ALLOW
            reason = "rollback_policy_allowed"
        elif policy_candidates and (warned or replay_policy.get("decision") == POLICY_WARN):
            decision = POLICY_WARN
            reason = "rollback_policy_warning"

        result = {
            "policy": "rollback",
            "decision": decision,
            "reason": reason,
            "candidate_count": len(policy_candidates),
            "allowed_count": len(allowed),
            "warn_count": len(warned),
            "candidates": policy_candidates,
            "action": "none",
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def evaluate_failed_execution_policy(
        self,
        source: Any,
        *,
        replay_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reasoning = self._reasoning_report(source)
        replay_policy = (
            self._safe_mapping(replay_policy)
            if replay_policy is not None
            else self.evaluate_replay_policy(reasoning)
        )
        failed = reasoning.failed_execution_recovery()
        raw_candidates = failed.get("candidates")
        if not isinstance(raw_candidates, list):
            raw_candidates = []
        policy_candidates = [
            self._classify_candidate(
                candidate,
                default_action_type="failed_execution_recovery",
                replay_policy=replay_policy,
            )
            for candidate in raw_candidates
            if isinstance(candidate, dict)
        ]
        allowed = [
            candidate
            for candidate in policy_candidates
            if candidate.get("decision") == POLICY_ALLOW
        ]
        warned = [
            candidate
            for candidate in policy_candidates
            if candidate.get("decision") == POLICY_WARN
        ]

        decision = POLICY_BLOCK
        reason = "no_failed_execution_recovery_candidates"
        if replay_policy.get("decision") == POLICY_BLOCK:
            reason = "replay_policy_blocks_failed_execution_recovery"
        elif allowed and replay_policy.get("decision") == POLICY_ALLOW:
            decision = POLICY_ALLOW
            reason = "failed_execution_recovery_policy_allowed"
        elif policy_candidates and (warned or replay_policy.get("decision") == POLICY_WARN):
            decision = POLICY_WARN
            reason = "failed_execution_recovery_policy_warning"

        result = {
            "policy": "failed_execution_recovery",
            "decision": decision,
            "reason": reason,
            "failed_execution_count": self._safe_int(failed.get("failed_execution_count"), 0),
            "candidate_count": len(policy_candidates),
            "allowed_count": len(allowed),
            "warn_count": len(warned),
            "candidates": policy_candidates,
            "action": "none",
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def classify_recovery_actions(
        self,
        policy_decisions: Any,
        *,
        replay_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        decisions = [
            copy.deepcopy(item)
            for item in policy_decisions
            if isinstance(item, dict)
        ] if isinstance(policy_decisions, list) else []
        allow_count = sum(1 for item in decisions if item.get("decision") == POLICY_ALLOW)
        warn_count = sum(1 for item in decisions if item.get("decision") == POLICY_WARN)
        block_count = sum(1 for item in decisions if item.get("decision") == POLICY_BLOCK)
        replay_decision = self._safe_text(self._safe_mapping(replay_policy).get("decision"))

        classification = POLICY_BLOCK
        if allow_count and not block_count and replay_decision == POLICY_ALLOW:
            classification = POLICY_ALLOW
        elif allow_count or warn_count:
            classification = POLICY_WARN

        result = {
            "classification": classification,
            "allow_count": allow_count,
            "warn_count": warn_count,
            "block_count": block_count,
            "decision_count": len(decisions),
            "action": "none",
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def _reasoning_report(self, source: Any) -> RuntimeRecoveryReasoningReport:
        if isinstance(source, RuntimeRecoveryReasoningReport):
            return RuntimeRecoveryReasoningReport(source.payload)
        if isinstance(source, RuntimeRecoveryPolicyReport):
            return RuntimeRecoveryReasoningReport({})
        return self.reasoner.reason(source)

    def _classify_candidate(
        self,
        candidate: dict[str, Any],
        *,
        default_action_type: str,
        replay_policy: dict[str, Any],
    ) -> dict[str, Any]:
        decision = POLICY_BLOCK
        reason = "candidate_not_safe_to_consider"
        if replay_policy.get("decision") == POLICY_BLOCK:
            reason = "blocked_by_replay_policy"
        elif not bool(candidate.get("safe_to_consider", False)):
            reason = "candidate_not_safe_to_consider"
        elif replay_policy.get("decision") == POLICY_WARN:
            decision = POLICY_WARN
            reason = "allowed_with_replay_policy_warning"
        else:
            decision = POLICY_ALLOW
            reason = "candidate_policy_allowed"

        result = {
            "candidate_id": self._safe_text(candidate.get("candidate_id")),
            "candidate_type": self._safe_text(candidate.get("candidate_type")) or default_action_type,
            "policy_action_type": default_action_type,
            "decision": decision,
            "reason": reason,
            "safe_to_consider": bool(candidate.get("safe_to_consider", False)),
            "source_classification": self._safe_text(candidate.get("classification")),
            "action": "none",
            "executes_action": False,
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def _policy_decisions_from(
        self,
        replay_policy: dict[str, Any],
        rollback_policy: dict[str, Any],
        failed_execution_policy: dict[str, Any],
    ) -> list[dict[str, Any]]:
        decisions = []
        for policy in (replay_policy, rollback_policy, failed_execution_policy):
            decision = {
                "policy": self._safe_text(policy.get("policy")),
                "decision": self._safe_text(policy.get("decision")),
                "reason": self._safe_text(policy.get("reason")),
                "action": "none",
            }
            decision["fingerprint"] = self._fingerprint(decision)
            decisions.append(decision)
        return decisions

    def _safe_mapping(self, value: Any) -> dict[str, Any]:
        return copy.deepcopy(value) if isinstance(value, dict) else {}

    def _safe_text(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    def _fingerprint(self, payload: dict[str, Any]) -> str:
        safe = copy.deepcopy(payload)
        safe.pop("fingerprint", None)
        encoded = json.dumps(
            safe,
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def evaluate_runtime_recovery_policy(source: Any) -> RuntimeRecoveryPolicyReport:
    return RuntimeRecoveryPolicyEvaluator().evaluate(source)


__all__ = [
    "POLICY_ALLOW",
    "POLICY_BLOCK",
    "POLICY_WARN",
    "RuntimeRecoveryPolicyEvaluator",
    "RuntimeRecoveryPolicyReport",
    "evaluate_runtime_recovery_policy",
]
