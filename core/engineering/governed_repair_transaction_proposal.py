from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GovernedRepairTransactionProposal:
    proposal_id: str
    recommendation_id: str
    verification_route_id: str
    repair_scope: list[str]
    allowed_mutation_targets: list[str]
    approval_required: bool
    rollback_required: bool
    verification_required: bool
    execution_allowed: bool
    mutation_allowed: bool
    repair_reason: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "recommendation_id": self.recommendation_id,
            "verification_route_id": self.verification_route_id,
            "repair_scope": list(self.repair_scope),
            "allowed_mutation_targets": list(self.allowed_mutation_targets),
            "approval_required": self.approval_required,
            "rollback_required": self.rollback_required,
            "verification_required": self.verification_required,
            "execution_allowed": self.execution_allowed,
            "mutation_allowed": self.mutation_allowed,
            "repair_reason": self.repair_reason,
            "metadata": dict(self.metadata),
        }


def build_governed_repair_transaction_proposal(
    recommendation: dict[str, Any],
    *,
    repair_scope: list[str],
    allowed_mutation_targets: list[str],
) -> GovernedRepairTransactionProposal:
    recommendation_id = str(recommendation.get("recommendation_id") or "").strip()
    verification_route_id = str(
        recommendation.get("verification_route_id") or ""
    ).strip()
    decision = str(recommendation.get("decision") or "").strip()
    metadata = dict(recommendation.get("metadata") or {})

    if not recommendation_id:
        raise ValueError("recommendation_id_required")
    if not verification_route_id:
        raise ValueError("verification_route_id_required")
    if metadata.get("control_plane_only") is not True:
        raise ValueError("recommendation_must_be_control_plane_only")
    if metadata.get("mutation_allowed") is not False:
        raise ValueError("recommendation_must_not_grant_mutation_authority")

    if decision not in {"recommend_repair", "retry_then_review"}:
        raise ValueError("repair_proposal_requires_repair_recommendation")

    clean_scope = [str(x).strip() for x in repair_scope if str(x).strip()]
    clean_targets = [
        str(x).strip() for x in allowed_mutation_targets if str(x).strip()
    ]

    if not clean_scope:
        raise ValueError("repair_scope_required")
    if not clean_targets:
        raise ValueError("allowed_mutation_targets_required")

    payload = {
        "recommendation_id": recommendation_id,
        "verification_route_id": verification_route_id,
        "repair_scope": clean_scope,
        "allowed_mutation_targets": clean_targets,
    }

    return GovernedRepairTransactionProposal(
        proposal_id="governed-repair-proposal-" + _stable_hash(payload)[:16],
        recommendation_id=recommendation_id,
        verification_route_id=verification_route_id,
        repair_scope=clean_scope,
        allowed_mutation_targets=clean_targets,
        approval_required=True,
        rollback_required=True,
        verification_required=True,
        execution_allowed=False,
        mutation_allowed=False,
        repair_reason=f"repair recommendation generated from decision={decision}",
        metadata={
            "control_plane_only": True,
            "read_only": True,
            "mutation_allowed": False,
            "execution_allowed": False,
            "patch_apply_allowed": False,
            "runtime_authority_granted": False,
            "canonical_runtime_success": False,
            "requires_governed_mutation_pipeline": True,
            "requires_rollback_eligibility": True,
            "requires_verification_before_success": True,
            "source_recommendation_metadata": metadata,
        },
    )


def validate_governed_repair_transaction_proposal_contract(
    payload: dict[str, Any],
) -> bool:
    required = {
        "proposal_id",
        "recommendation_id",
        "verification_route_id",
        "repair_scope",
        "allowed_mutation_targets",
        "approval_required",
        "rollback_required",
        "verification_required",
        "execution_allowed",
        "mutation_allowed",
        "repair_reason",
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

    forbidden = {
        "runtime_evidence_id",
        "runtime_audit_metadata",
        "governed_mutation_lineage",
        "execution_summary",
        "canonical_success",
    }

    if forbidden.intersection(payload):
        return False

    return True


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
