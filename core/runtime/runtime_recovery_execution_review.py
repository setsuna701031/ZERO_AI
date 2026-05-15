from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.runtime.runtime_recovery_execution_contract import (
    CONTRACT_STATUS_APPROVED,
    CONTRACT_STATUS_BLOCKED,
    CONTRACT_STATUS_DEFERRED,
    RuntimeRecoveryExecutionContractReport,
)
from core.runtime.runtime_recovery_operator_summary import (
    build_runtime_recovery_operator_summary,
)


REVIEW_READY = "ready_for_confirmation"
REVIEW_BLOCKED = "blocked"
REVIEW_DEFERRED = "deferred"


class RuntimeRecoveryExecutionReviewReport:
    SCHEMA = "zero.runtime.recovery_execution_review.v1"

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = self._json_safe(payload)

    @property
    def payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload)

    @property
    def fingerprint(self) -> str:
        return str(self._payload.get("fingerprint") or "")

    def review_summary(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("review_summary", {}))

    def operator_summary(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("operator_summary", {}))

    def risk_summary(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("risk_summary", {}))

    def lineage_trust_review(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("lineage_trust_review", {}))

    def replay_integrity_review(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("replay_integrity_review", {}))

    def policy_reason_review(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("policy_reason_review", {}))

    def blocked_deferred_review(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("blocked_deferred_review", {}))

    def confirmation_review(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("confirmation_review", {}))

    def contract_reviews(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("contract_reviews", []))

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


class RuntimeRecoveryExecutionReviewer:
    """Read-only review reports over recovery execution contracts."""

    def review(self, source: Any) -> RuntimeRecoveryExecutionReviewReport:
        contract_report = self._contract_report(source)
        contract_reviews = self.generate_execution_contract_reviews(contract_report)
        risk_summary = self.report_risk_summary(contract_report, contract_reviews)
        lineage_trust_review = self.review_lineage_trust(contract_report, contract_reviews)
        replay_integrity_review = self.review_replay_integrity(contract_report, contract_reviews)
        policy_reason_review = self.review_policy_reasons(contract_report)
        blocked_deferred_review = self.report_blocked_deferred_explanations(contract_report, contract_reviews)
        confirmation_review = self.review_confirmation_requirements(contract_report, contract_reviews)
        review_summary = self._review_summary(
            contract_report=contract_report,
            contract_reviews=contract_reviews,
            risk_summary=risk_summary,
            blocked_deferred_review=blocked_deferred_review,
            confirmation_review=confirmation_review,
        )
        operator_gate_result = {
            "ok": self._safe_text(review_summary.get("state")) == REVIEW_READY,
            "blocked": self._safe_text(review_summary.get("state")) == REVIEW_BLOCKED,
            "blockers": [
                self._safe_text(item.get("reason") or item.get("contract_id"))
                for item in self._safe_review_list(blocked_deferred_review.get("explanations"))
            ],
            "reports": {
                "contract": review_summary,
                "approval": confirmation_review,
            },
        }
        operator_summary = build_runtime_recovery_operator_summary(operator_gate_result)

        payload = {
            "ok": True,
            "schema": RuntimeRecoveryExecutionReviewReport.SCHEMA,
            "mode": "review_report_only",
            "read_only": True,
            "executes_recovery": False,
            "executes_rollback": False,
            "executes_repair": False,
            "source": {
                "execution_contract_fingerprint": contract_report.fingerprint,
            },
            "review_summary": review_summary,
            "operator_summary": operator_summary,
            "risk_summary": risk_summary,
            "lineage_trust_review": lineage_trust_review,
            "replay_integrity_review": replay_integrity_review,
            "policy_reason_review": policy_reason_review,
            "blocked_deferred_review": blocked_deferred_review,
            "confirmation_review": confirmation_review,
            "contract_reviews": contract_reviews,
        }
        payload["fingerprint"] = self._fingerprint(payload)
        return RuntimeRecoveryExecutionReviewReport(payload)

    def generate_execution_contract_reviews(
        self,
        source: RuntimeRecoveryExecutionContractReport | Any,
    ) -> list[dict[str, Any]]:
        contract_report = self._contract_report(source)
        reviews = []
        for contract in self._all_contracts(contract_report):
            contract_id = self._safe_text(contract.get("contract_id"))
            status = self._safe_text(contract.get("status"))
            review = {
                "review_id": f"review:{contract_id}",
                "contract_id": contract_id,
                "contract_type": self._safe_text(contract.get("contract_type")),
                "status": status,
                "review_state": self._review_state_for_status(status),
                "approval_state": self._safe_text(contract.get("approval_state")),
                "approval_reason": self._safe_text(contract.get("approval_reason")),
                "executable": bool(contract.get("executable", False)),
                "requires_confirmation": bool(contract.get("requires_confirmation", False)),
                "risk_profile": self._safe_text(self._safe_mapping(contract.get("risk")).get("risk_profile")),
                "guard_ok": self._guards_ok(contract),
                "action": "none",
                "executes_action": False,
            }
            review["fingerprint"] = self._fingerprint(review)
            reviews.append(review)
        return sorted(reviews, key=lambda item: self._safe_text(item.get("review_id")))

    def report_risk_summary(
        self,
        source: RuntimeRecoveryExecutionContractReport | Any,
        contract_reviews: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        contract_report = self._contract_report(source)
        reviews = self._safe_review_list(contract_reviews) if contract_reviews is not None else self.generate_execution_contract_reviews(contract_report)
        contracts = self._all_contracts(contract_report)
        guard_failures = [
            self._safe_text(review.get("contract_id"))
            for review in reviews
            if not bool(review.get("guard_ok", False))
        ]
        executable_contracts = [
            self._safe_text(contract.get("contract_id"))
            for contract in contracts
            if bool(contract.get("executable", False)) or bool(contract.get("executes_action", False))
        ]
        result = {
            "review": "risk_summary",
            "risk_profile": "execution_contract_only",
            "contract_count": len(contracts),
            "guard_failure_count": len(guard_failures),
            "guard_failures": sorted(guard_failures),
            "executable_contract_count": len(executable_contracts),
            "executable_contracts": sorted(executable_contracts),
            "all_executable_false": not executable_contracts,
            "all_guards_ok": not guard_failures,
            "action": "none",
            "executes_action": False,
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def review_lineage_trust(
        self,
        source: RuntimeRecoveryExecutionContractReport | Any,
        contract_reviews: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        contract_report = self._contract_report(source)
        reviews = self._safe_review_list(contract_reviews) if contract_reviews is not None else self.generate_execution_contract_reviews(contract_report)
        blocked_reasons = [
            self._safe_text(review.get("approval_reason"))
            for review in reviews
            if "lineage" in self._safe_text(review.get("approval_reason"))
        ]
        if blocked_reasons:
            state = REVIEW_BLOCKED
            reason = "lineage_related_block_present"
        elif contract_report.blocked_contracts() and not contract_report.replay_contracts():
            state = REVIEW_BLOCKED
            reason = "lineage_or_evidence_isolation_present"
        else:
            state = REVIEW_READY
            reason = "no_lineage_block_in_contracts"
        result = {
            "review": "lineage_trust",
            "state": state,
            "reason": reason,
            "lineage_related_reasons": sorted(set(blocked_reasons)),
            "action": "none",
            "executes_action": False,
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def review_replay_integrity(
        self,
        source: RuntimeRecoveryExecutionContractReport | Any,
        contract_reviews: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        contract_report = self._contract_report(source)
        replay_contracts = contract_report.replay_contracts()
        blocked_replay = [
            contract
            for contract in contract_report.blocked_contracts()
            if "replay" in self._safe_text(contract.get("contract_id"))
            or "replay" in self._safe_text(contract.get("approval_reason"))
        ]
        replay_safety = [
            self._safe_text(self._safe_mapping(contract.get("metadata")).get("replay_safety"))
            for contract in replay_contracts
            if isinstance(contract, dict)
        ]
        trust_scores = [
            self._safe_int(self._safe_mapping(contract.get("metadata")).get("trust_score"), 0)
            for contract in replay_contracts
            if isinstance(contract, dict)
        ]
        if blocked_replay:
            state = REVIEW_BLOCKED
            reason = "replay_block_or_defer_present"
        elif not replay_contracts:
            state = REVIEW_DEFERRED
            reason = "no_replay_contract_to_review"
        elif all(value == "replay_safe" for value in replay_safety) and all(value >= 90 for value in trust_scores):
            state = REVIEW_READY
            reason = "replay_integrity_review_passed"
        else:
            state = REVIEW_DEFERRED
            reason = "replay_integrity_requires_review"
        result = {
            "review": "replay_integrity",
            "state": state,
            "reason": reason,
            "replay_contract_count": len(replay_contracts),
            "replay_safety": replay_safety,
            "trust_scores": trust_scores,
            "blocked_replay_count": len(blocked_replay),
            "action": "none",
            "executes_action": False,
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def review_policy_reasons(
        self,
        source: RuntimeRecoveryExecutionContractReport | Any,
    ) -> dict[str, Any]:
        contract_report = self._contract_report(source)
        approval_snapshot = contract_report.approval_snapshot()
        reasons = approval_snapshot.get("approval_reasons")
        if not isinstance(reasons, list):
            reasons = []
        safe_reasons = [
            {
                "gate": self._safe_text(reason.get("gate")),
                "state": self._safe_text(reason.get("state")),
                "reason": self._safe_text(reason.get("reason")),
            }
            for reason in reasons
            if isinstance(reason, dict)
        ]
        result = {
            "review": "policy_reasons",
            "approval_state": self._safe_text(approval_snapshot.get("approval_state")),
            "approval_reason": self._safe_text(approval_snapshot.get("approval_reason")),
            "reason_count": len(safe_reasons),
            "reasons": safe_reasons,
            "action": "none",
            "executes_action": False,
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def report_blocked_deferred_explanations(
        self,
        source: RuntimeRecoveryExecutionContractReport | Any,
        contract_reviews: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        contract_report = self._contract_report(source)
        reviews = self._safe_review_list(contract_reviews) if contract_reviews is not None else self.generate_execution_contract_reviews(contract_report)
        explanations = [
            {
                "contract_id": self._safe_text(review.get("contract_id")),
                "state": self._safe_text(review.get("review_state")),
                "reason": self._safe_text(review.get("approval_reason")),
            }
            for review in reviews
            if self._safe_text(review.get("review_state")) in {REVIEW_BLOCKED, REVIEW_DEFERRED}
        ]
        state = REVIEW_READY
        if any(item["state"] == REVIEW_BLOCKED for item in explanations):
            state = REVIEW_BLOCKED
        elif explanations:
            state = REVIEW_DEFERRED
        result = {
            "review": "blocked_deferred",
            "state": state,
            "explanation_count": len(explanations),
            "explanations": sorted(explanations, key=lambda item: item["contract_id"]),
            "action": "none",
            "executes_action": False,
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def review_confirmation_requirements(
        self,
        source: RuntimeRecoveryExecutionContractReport | Any,
        contract_reviews: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        contract_report = self._contract_report(source)
        contracts = self._all_contracts(contract_report)
        missing_confirmation = [
            self._safe_text(contract.get("contract_id"))
            for contract in contracts
            if not bool(contract.get("requires_confirmation", False))
        ]
        executable_contracts = [
            self._safe_text(contract.get("contract_id"))
            for contract in contracts
            if bool(contract.get("executable", False)) or bool(contract.get("executes_action", False))
        ]
        state = REVIEW_READY
        reason = "confirmation_required_for_all_contracts"
        if missing_confirmation or executable_contracts:
            state = REVIEW_BLOCKED
            reason = "confirmation_requirements_failed"
        result = {
            "review": "confirmation_requirements",
            "state": state,
            "reason": reason,
            "contract_count": len(contracts),
            "missing_confirmation_count": len(missing_confirmation),
            "missing_confirmation_contracts": sorted(missing_confirmation),
            "executable_contract_count": len(executable_contracts),
            "executable_contracts": sorted(executable_contracts),
            "action": "none",
            "executes_action": False,
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def _review_summary(
        self,
        *,
        contract_report: RuntimeRecoveryExecutionContractReport,
        contract_reviews: list[dict[str, Any]],
        risk_summary: dict[str, Any],
        blocked_deferred_review: dict[str, Any],
        confirmation_review: dict[str, Any],
    ) -> dict[str, Any]:
        if not bool(risk_summary.get("all_executable_false", False)):
            state = REVIEW_BLOCKED
            reason = "contract_risk_review_failed"
        elif self._safe_text(confirmation_review.get("state")) == REVIEW_BLOCKED:
            state = REVIEW_BLOCKED
            reason = "confirmation_review_failed"
        elif self._safe_text(blocked_deferred_review.get("state")) == REVIEW_BLOCKED:
            state = REVIEW_BLOCKED
            reason = "blocked_contracts_require_attention"
        elif self._safe_text(blocked_deferred_review.get("state")) == REVIEW_DEFERRED:
            state = REVIEW_DEFERRED
            reason = "deferred_contracts_require_attention"
        else:
            state = REVIEW_READY
            reason = "execution_contracts_ready_for_confirmation"
        summary = {
            "state": state,
            "reason": reason,
            "contract_fingerprint": contract_report.fingerprint,
            "review_count": len(contract_reviews),
            "action": "none",
            "executes_action": False,
        }
        summary["fingerprint"] = self._fingerprint(summary)
        return summary

    def _contract_report(self, source: Any) -> RuntimeRecoveryExecutionContractReport:
        if isinstance(source, RuntimeRecoveryExecutionContractReport):
            return RuntimeRecoveryExecutionContractReport(source.payload)
        return RuntimeRecoveryExecutionContractReport({})

    def _all_contracts(self, report: RuntimeRecoveryExecutionContractReport) -> list[dict[str, Any]]:
        contracts = []
        recovery = report.recovery_contract()
        if recovery:
            contracts.append(recovery)
        contracts.extend(report.replay_contracts())
        contracts.extend(report.rollback_contracts())
        contracts.extend(report.failed_execution_contracts())
        contracts.extend(report.blocked_contracts())
        return [
            copy.deepcopy(contract)
            for contract in contracts
            if isinstance(contract, dict)
        ]

    def _review_state_for_status(self, status: str) -> str:
        if status == CONTRACT_STATUS_APPROVED:
            return REVIEW_READY
        if status == CONTRACT_STATUS_DEFERRED:
            return REVIEW_DEFERRED
        return REVIEW_BLOCKED

    def _guards_ok(self, contract: dict[str, Any]) -> bool:
        risk = self._safe_mapping(contract.get("risk"))
        guards = self._safe_mapping(risk.get("guards"))
        expected = (
            "no_runtime_execution",
            "no_rollback_execution",
            "no_repair_execution",
            "no_scheduler_invocation",
            "no_persistence",
            "no_networking",
        )
        return all(bool(guards.get(name, False)) for name in expected)

    def _safe_review_list(self, value: Any) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(item)
            for item in value
            if isinstance(item, dict)
        ] if isinstance(value, list) else []

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


def review_runtime_recovery_execution_contract(source: Any) -> RuntimeRecoveryExecutionReviewReport:
    return RuntimeRecoveryExecutionReviewer().review(source)


__all__ = [
    "REVIEW_BLOCKED",
    "REVIEW_DEFERRED",
    "REVIEW_READY",
    "RuntimeRecoveryExecutionReviewReport",
    "RuntimeRecoveryExecutionReviewer",
    "review_runtime_recovery_execution_contract",
]
