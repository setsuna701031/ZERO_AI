from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RetryRepairRecommendation:
    recommendation_id: str
    source_bundle_id: str
    verification_route_id: str
    decision: str
    retry_allowed: bool
    repair_recommended: bool
    escalation_required: bool
    approval_required: bool
    reason: str
    retry_budget: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "source_bundle_id": self.source_bundle_id,
            "verification_route_id": self.verification_route_id,
            "decision": self.decision,
            "retry_allowed": self.retry_allowed,
            "repair_recommended": self.repair_recommended,
            "escalation_required": self.escalation_required,
            "approval_required": self.approval_required,
            "reason": self.reason,
            "retry_budget": dict(self.retry_budget),
            "metadata": dict(self.metadata),
        }


def build_retry_repair_recommendation(
    evidence_bundle: dict[str, Any],
    *,
    attempt_index: int = 0,
    max_retries: int = 2,
) -> RetryRepairRecommendation:
    """Build a non-executing retry/repair recommendation from verification evidence.

    This object does not retry, repair, execute, mutate, or approve anything.
    It only classifies the next recommended control-plane action.
    """

    bundle_id = str(evidence_bundle.get("bundle_id") or "").strip()
    route_id = str(evidence_bundle.get("verification_route_id") or "").strip()
    metadata = dict(evidence_bundle.get("metadata") or {})
    failure = str(evidence_bundle.get("failure_classification") or "").strip()
    status = str(evidence_bundle.get("status") or "").strip()

    if not bundle_id:
        raise ValueError("source_bundle_id_required")
    if not route_id:
        raise ValueError("verification_route_id_required")
    if metadata.get("verification_only") is not True:
        raise ValueError("evidence_bundle_must_be_verification_only")
    if metadata.get("canonical_runtime_success") is not False:
        raise ValueError("evidence_bundle_must_not_claim_runtime_success")
    if metadata.get("mutation_allowed") is not False:
        raise ValueError("evidence_bundle_must_not_grant_mutation_authority")

    attempt = max(0, int(attempt_index))
    budget_limit = max(0, int(max_retries))
    retries_remaining = max(0, budget_limit - attempt)

    decision, reason = _decision_for(
        status=status,
        failure=failure,
        retries_remaining=retries_remaining,
    )
    retry_allowed = decision in {"retry_verification", "retry_then_review"}
    repair_recommended = decision in {"recommend_repair", "retry_then_review"}
    escalation_required = decision in {"escalate_to_user", "hard_stop"}
    approval_required = repair_recommended or escalation_required

    retry_budget = {
        "attempt_index": attempt,
        "max_retries": budget_limit,
        "retries_remaining": retries_remaining,
    }

    payload = {
        "source_bundle_id": bundle_id,
        "verification_route_id": route_id,
        "decision": decision,
        "retry_allowed": retry_allowed,
        "repair_recommended": repair_recommended,
        "escalation_required": escalation_required,
        "approval_required": approval_required,
        "reason": reason,
        "retry_budget": retry_budget,
    }

    return RetryRepairRecommendation(
        recommendation_id="retry-repair-recommendation-" + _stable_hash(payload)[:16],
        source_bundle_id=bundle_id,
        verification_route_id=route_id,
        decision=decision,
        retry_allowed=retry_allowed,
        repair_recommended=repair_recommended,
        escalation_required=escalation_required,
        approval_required=approval_required,
        reason=reason,
        retry_budget=retry_budget,
        metadata={
            "control_plane_only": True,
            "read_only": True,
            "mutation_allowed": False,
            "execution_allowed": False,
            "patch_apply_allowed": False,
            "runtime_authority_granted": False,
            "canonical_runtime_success": False,
            "requires_governed_repair_transaction_for_mutation": True,
            "source_evidence_metadata": metadata,
        },
    )


def validate_retry_repair_recommendation_contract(payload: dict[str, Any]) -> bool:
    required = {
        "recommendation_id",
        "source_bundle_id",
        "verification_route_id",
        "decision",
        "retry_allowed",
        "repair_recommended",
        "escalation_required",
        "approval_required",
        "reason",
        "retry_budget",
        "metadata",
    }
    if not required.issubset(payload):
        return False

    metadata = payload.get("metadata") or {}
    if metadata.get("control_plane_only") is not True:
        return False
    if metadata.get("mutation_allowed") is not False:
        return False
    if metadata.get("execution_allowed") is not False:
        return False
    if metadata.get("runtime_authority_granted") is not False:
        return False
    if metadata.get("canonical_runtime_success") is not False:
        return False

    forbidden_success_fields = {
        "runtime_evidence_id",
        "runtime_audit_metadata",
        "governed_mutation_lineage",
        "verification_result",
        "rollback_eligibility",
        "recovery_eligibility",
        "execution_summary",
        "canonical_success",
    }
    if forbidden_success_fields.intersection(payload):
        return False

    return True


def _decision_for(
    *,
    status: str,
    failure: str,
    retries_remaining: int,
) -> tuple[str, str]:
    if status == "passed" or failure == "none":
        return "no_action", "verification passed"

    if failure == "timeout":
        if retries_remaining > 0:
            return "retry_verification", "timeout may be environmental; retry verification first"
        return "escalate_to_user", "timeout retry budget exhausted"

    if failure in {"test_failure", "compile_failure", "lint_failure", "runtime_error"}:
        if retries_remaining > 0:
            return "retry_then_review", "retry once before governed repair recommendation"
        return "recommend_repair", "verification failure is repair eligible after retry budget"

    if failure == "unknown_failure":
        if retries_remaining > 0:
            return "retry_verification", "unknown verification failure; retry before escalation"
        return "escalate_to_user", "unknown verification failure with no retries remaining"

    return "hard_stop", f"unsupported verification failure classification: {failure}"


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
