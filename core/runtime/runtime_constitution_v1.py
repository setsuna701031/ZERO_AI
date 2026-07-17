from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any


CONSTITUTION_LEGAL = "constitutional_legal"
CONSTITUTION_REVIEW_REQUIRED = "constitutional_review_required"
CONSTITUTION_ILLEGAL = "constitutional_illegal"


@dataclass(frozen=True)
class RuntimeConstitutionDecision:
    decision_id: str
    replay_id: str
    legality: str
    legal: bool
    review_required: bool
    illegal: bool
    continuation_allowed: bool
    classification: str
    reason: str
    violations: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "replay_id": self.replay_id,
            "legality": self.legality,
            "legal": self.legal,
            "review_required": self.review_required,
            "illegal": self.illegal,
            "continuation_allowed": self.continuation_allowed,
            "classification": self.classification,
            "reason": self.reason,
            "violations": list(self.violations),
            "evidence": copy.deepcopy(self.evidence),
        }


class RuntimeConstitutionV1:
    def evaluate_ledger_entry(
        self,
        ledger_entry: Any,
    ) -> RuntimeConstitutionDecision:
        payload = (
            ledger_entry.to_dict()
            if hasattr(ledger_entry, "to_dict")
            else dict(ledger_entry)
        )

        replay_id = str(payload.get("replay_id") or "")
        classification = str(payload.get("classification") or "")
        closure_status = str(payload.get("closure_status") or "")
        continuation_allowed = bool(payload.get("continuation_allowed"))

        evidence_bundle = (
            copy.deepcopy(payload.get("evidence_bundle"))
            if isinstance(payload.get("evidence_bundle"), dict)
            else {}
        )

        violations = self._detect_violations(
            payload=payload,
            evidence_bundle=evidence_bundle,
        )

        if violations:
            return RuntimeConstitutionDecision(
                decision_id=f"constitution::{replay_id}",
                replay_id=replay_id,
                legality=CONSTITUTION_ILLEGAL,
                legal=False,
                review_required=False,
                illegal=True,
                continuation_allowed=False,
                classification="constitutional_violation",
                reason="runtime_constitution_violation",
                violations=violations,
                evidence={
                    "ledger_entry": payload,
                    "source": "runtime_constitution_v1",
                },
            )

        if (
            classification == "governance_review_required"
            or closure_status == "runtime_review_required"
        ):
            return RuntimeConstitutionDecision(
                decision_id=f"constitution::{replay_id}",
                replay_id=replay_id,
                legality=CONSTITUTION_REVIEW_REQUIRED,
                legal=False,
                review_required=True,
                illegal=False,
                continuation_allowed=False,
                classification="constitutional_review_required",
                reason="runtime_requires_constitutional_review",
                violations=[],
                evidence={
                    "ledger_entry": payload,
                    "source": "runtime_constitution_v1",
                },
            )

        return RuntimeConstitutionDecision(
            decision_id=f"constitution::{replay_id}",
            replay_id=replay_id,
            legality=CONSTITUTION_LEGAL,
            legal=True,
            review_required=False,
            illegal=False,
            continuation_allowed=continuation_allowed,
            classification="constitutional_legal",
            reason="runtime_constitution_verified",
            violations=[],
            evidence={
                "ledger_entry": payload,
                "source": "runtime_constitution_v1",
            },
        )

    def evaluate_ledger_chain(
        self,
        ledger: Any,
    ) -> dict[str, Any]:
        if hasattr(ledger, "verify_chain_integrity"):
            integrity = ledger.verify_chain_integrity()
        else:
            integrity = {"verified": False, "reason": "ledger_not_verifiable"}

        if not integrity.get("verified"):
            return {
                "legality": CONSTITUTION_ILLEGAL,
                "legal": False,
                "review_required": False,
                "illegal": True,
                "continuation_allowed": False,
                "classification": "constitutional_ledger_integrity_failed",
                "reason": integrity.get("reason", "ledger_integrity_failed"),
                "decisions": [],
                "integrity": integrity,
            }

        entries = (
            ledger.get_entries()
            if hasattr(ledger, "get_entries")
            else []
        )

        decisions = [
            self.evaluate_ledger_entry(entry)
            for entry in entries
        ]

        if any(item.illegal for item in decisions):
            legality = CONSTITUTION_ILLEGAL
            classification = "constitutional_violation"
            legal = False
            review_required = False
            illegal = True
            continuation_allowed = False
            reason = "one_or_more_runtime_entries_are_illegal"
        elif any(item.review_required for item in decisions):
            legality = CONSTITUTION_REVIEW_REQUIRED
            classification = "constitutional_review_required"
            legal = False
            review_required = True
            illegal = False
            continuation_allowed = False
            reason = "one_or_more_runtime_entries_require_review"
        else:
            legality = CONSTITUTION_LEGAL
            classification = "constitutional_legal"
            legal = True
            review_required = False
            illegal = False
            continuation_allowed = all(
                item.continuation_allowed
                for item in decisions
            ) if decisions else True
            reason = "runtime_ledger_chain_constitutionally_verified"

        return {
            "legality": legality,
            "legal": legal,
            "review_required": review_required,
            "illegal": illegal,
            "continuation_allowed": continuation_allowed,
            "classification": classification,
            "reason": reason,
            "decisions": [
                item.to_dict()
                for item in decisions
            ],
            "integrity": integrity,
        }

    def _detect_violations(
        self,
        *,
        payload: dict[str, Any],
        evidence_bundle: dict[str, Any],
    ) -> list[str]:
        violations: list[str] = []

        classification = str(payload.get("classification") or "")
        closure_status = str(payload.get("closure_status") or "")
        continuation_allowed = bool(payload.get("continuation_allowed"))
        immutable = bool(payload.get("immutable"))

        closure_snapshot = (
            evidence_bundle.get("closure_snapshot")
            if isinstance(evidence_bundle.get("closure_snapshot"), dict)
            else {}
        )

        seal_snapshot = (
            evidence_bundle.get("seal_snapshot")
            if isinstance(evidence_bundle.get("seal_snapshot"), dict)
            else {}
        )

        if not immutable:
            violations.append("ledger_entry_not_immutable")

        if (
            classification == "governance_failed"
            and continuation_allowed
        ):
            violations.append("failed_runtime_continuation_allowed")

        if (
            closure_status == "runtime_blocked"
            and continuation_allowed
        ):
            violations.append("blocked_runtime_continuation_allowed")

        if (
            bool(closure_snapshot.get("blocked"))
            and continuation_allowed
        ):
            violations.append("blocked_closure_continuation_allowed")

        if (
            str(seal_snapshot.get("seal_status") or "") == "sealed_failed"
            and continuation_allowed
        ):
            violations.append("failed_seal_continuation_allowed")

        if (
            bool(seal_snapshot.get("failed"))
            and continuation_allowed
        ):
            violations.append("failed_recovery_reopened")

        if (
            bool(closure_snapshot.get("reopen_protection"))
            and classification == "governance_failed"
            and continuation_allowed
        ):
            violations.append("reopen_protection_bypassed")

        return sorted(set(violations))