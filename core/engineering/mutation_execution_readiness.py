from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MutationExecutionReadiness:
    readiness_id: str
    repair_proposal_id: str
    recommendation_id: str
    verification_route_id: str
    ready_for_governed_mutation: bool
    approval_complete: bool
    rollback_available: bool
    verification_profile_available: bool
    mutation_scope_locked: bool
    blockers: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "readiness_id": self.readiness_id,
            "repair_proposal_id": self.repair_proposal_id,
            "recommendation_id": self.recommendation_id,
            "verification_route_id": self.verification_route_id,
            "ready_for_governed_mutation": self.ready_for_governed_mutation,
            "approval_complete": self.approval_complete,
            "rollback_available": self.rollback_available,
            "verification_profile_available": self.verification_profile_available,
            "mutation_scope_locked": self.mutation_scope_locked,
            "blockers": list(self.blockers),
            "metadata": dict(self.metadata),
        }


def build_mutation_execution_readiness(
    repair_proposal: dict[str, Any],
    *,
    approval_complete: bool,
    rollback_available: bool,
    verification_profile_available: bool,
) -> MutationExecutionReadiness:
    """Assess whether a repair proposal may enter governed mutation.

    This does not apply patches, execute commands, mutate files, or grant runtime
    authority. It only determines whether a proposal has the required envelope to
    be submitted to the governed mutation pipeline later.
    """

    proposal_id = str(repair_proposal.get("proposal_id") or "").strip()
    recommendation_id = str(repair_proposal.get("recommendation_id") or "").strip()
    verification_route_id = str(
        repair_proposal.get("verification_route_id") or ""
    ).strip()
    metadata = dict(repair_proposal.get("metadata") or {})

    if not proposal_id:
        raise ValueError("repair_proposal_id_required")
    if not recommendation_id:
        raise ValueError("recommendation_id_required")
    if not verification_route_id:
        raise ValueError("verification_route_id_required")
    if metadata.get("requires_governed_mutation_pipeline") is not True:
        raise ValueError("repair_proposal_must_require_governed_mutation_pipeline")
    if metadata.get("mutation_allowed") is not False:
        raise ValueError("repair_proposal_must_not_grant_mutation_authority")
    if metadata.get("execution_allowed") is not False:
        raise ValueError("repair_proposal_must_not_grant_execution_authority")

    repair_scope = repair_proposal.get("repair_scope") or []
    targets = repair_proposal.get("allowed_mutation_targets") or []
    mutation_scope_locked = bool(repair_scope) and bool(targets)

    blockers: list[str] = []
    if not approval_complete:
        blockers.append("approval_incomplete")
    if not rollback_available:
        blockers.append("rollback_unavailable")
    if not verification_profile_available:
        blockers.append("verification_profile_unavailable")
    if not mutation_scope_locked:
        blockers.append("mutation_scope_unlocked")

    ready = not blockers

    payload = {
        "repair_proposal_id": proposal_id,
        "recommendation_id": recommendation_id,
        "verification_route_id": verification_route_id,
        "approval_complete": bool(approval_complete),
        "rollback_available": bool(rollback_available),
        "verification_profile_available": bool(verification_profile_available),
        "mutation_scope_locked": mutation_scope_locked,
        "blockers": blockers,
    }

    return MutationExecutionReadiness(
        readiness_id="mutation-readiness-" + _stable_hash(payload)[:16],
        repair_proposal_id=proposal_id,
        recommendation_id=recommendation_id,
        verification_route_id=verification_route_id,
        ready_for_governed_mutation=ready,
        approval_complete=bool(approval_complete),
        rollback_available=bool(rollback_available),
        verification_profile_available=bool(verification_profile_available),
        mutation_scope_locked=mutation_scope_locked,
        blockers=tuple(blockers),
        metadata={
            "control_plane_only": True,
            "read_only": True,
            "mutation_allowed": False,
            "execution_allowed": False,
            "patch_apply_allowed": False,
            "runtime_authority_granted": False,
            "canonical_runtime_success": False,
            "governed_mutation_pipeline_required": True,
            "requires_runtime_evidence_after_execution": True,
            "requires_audit_lineage_after_execution": True,
            "source_repair_proposal_metadata": metadata,
        },
    )


def validate_mutation_execution_readiness_contract(payload: dict[str, Any]) -> bool:
    required = {
        "readiness_id",
        "repair_proposal_id",
        "recommendation_id",
        "verification_route_id",
        "ready_for_governed_mutation",
        "approval_complete",
        "rollback_available",
        "verification_profile_available",
        "mutation_scope_locked",
        "blockers",
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

    ready = payload.get("ready_for_governed_mutation") is True
    blockers = payload.get("blockers") or []
    if ready and blockers:
        return False
    if ready:
        if payload.get("approval_complete") is not True:
            return False
        if payload.get("rollback_available") is not True:
            return False
        if payload.get("verification_profile_available") is not True:
            return False
        if payload.get("mutation_scope_locked") is not True:
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
