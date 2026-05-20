from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GovernedApplyRequest:
    apply_request_id: str
    readiness_id: str
    repair_proposal_id: str
    verification_route_id: str
    approved_by: str
    target_files: tuple[str, ...]
    dry_run_required: bool
    sandbox_required: bool
    rollback_checkpoint_required: bool
    verification_required: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "apply_request_id": self.apply_request_id,
            "readiness_id": self.readiness_id,
            "repair_proposal_id": self.repair_proposal_id,
            "verification_route_id": self.verification_route_id,
            "approved_by": self.approved_by,
            "target_files": list(self.target_files),
            "dry_run_required": self.dry_run_required,
            "sandbox_required": self.sandbox_required,
            "rollback_checkpoint_required": self.rollback_checkpoint_required,
            "verification_required": self.verification_required,
            "metadata": dict(self.metadata),
        }


def build_governed_apply_request(
    readiness: dict[str, Any],
    *,
    approved_by: str,
) -> GovernedApplyRequest:
    """Build a governed apply request envelope from mutation readiness.

    This function does not apply patches, write files, run commands, or grant raw
    execution authority. It only packages a fully gated readiness artifact for a
    future governed mutation executor.
    """

    readiness_id = str(readiness.get("readiness_id") or "").strip()
    repair_proposal_id = str(readiness.get("repair_proposal_id") or "").strip()
    verification_route_id = str(readiness.get("verification_route_id") or "").strip()
    metadata = dict(readiness.get("metadata") or {})
    approved_actor = str(approved_by or "").strip()

    if not readiness_id:
        raise ValueError("readiness_id_required")
    if not repair_proposal_id:
        raise ValueError("repair_proposal_id_required")
    if not verification_route_id:
        raise ValueError("verification_route_id_required")
    if not approved_actor:
        raise ValueError("approved_by_required")
    if readiness.get("ready_for_governed_mutation") is not True:
        raise ValueError("readiness_not_ready_for_governed_mutation")
    if metadata.get("governed_mutation_pipeline_required") is not True:
        raise ValueError("readiness_must_require_governed_mutation_pipeline")
    if metadata.get("mutation_allowed") is not False:
        raise ValueError("readiness_must_not_grant_mutation_authority")
    if metadata.get("execution_allowed") is not False:
        raise ValueError("readiness_must_not_grant_execution_authority")

    source_proposal_metadata = dict(metadata.get("source_repair_proposal_metadata") or {})
    source_targets = (
        source_proposal_metadata.get("allowed_mutation_targets")
        or readiness.get("allowed_mutation_targets")
        or []
    )
    target_files = tuple(str(item).strip() for item in source_targets if str(item).strip())

    payload = {
        "readiness_id": readiness_id,
        "repair_proposal_id": repair_proposal_id,
        "verification_route_id": verification_route_id,
        "approved_by": approved_actor,
        "target_files": list(target_files),
    }

    return GovernedApplyRequest(
        apply_request_id="governed-apply-request-" + _stable_hash(payload)[:16],
        readiness_id=readiness_id,
        repair_proposal_id=repair_proposal_id,
        verification_route_id=verification_route_id,
        approved_by=approved_actor,
        target_files=target_files,
        dry_run_required=True,
        sandbox_required=True,
        rollback_checkpoint_required=True,
        verification_required=True,
        metadata={
            "control_plane_only": True,
            "request_only": True,
            "mutation_allowed": False,
            "execution_allowed": False,
            "patch_apply_allowed": False,
            "runtime_authority_granted": False,
            "canonical_runtime_success": False,
            "requires_governed_runtime_execution": True,
            "requires_sandbox_apply": True,
            "requires_rollback_checkpoint": True,
            "requires_verification_after_apply": True,
            "requires_runtime_evidence_after_execution": True,
            "requires_audit_lineage_after_execution": True,
            "source_readiness_metadata": metadata,
        },
    )


def validate_governed_apply_request_contract(payload: dict[str, Any]) -> bool:
    required = {
        "apply_request_id",
        "readiness_id",
        "repair_proposal_id",
        "verification_route_id",
        "approved_by",
        "target_files",
        "dry_run_required",
        "sandbox_required",
        "rollback_checkpoint_required",
        "verification_required",
        "metadata",
    }
    if not required.issubset(payload):
        return False

    metadata = payload.get("metadata") or {}
    if metadata.get("control_plane_only") is not True:
        return False
    if metadata.get("request_only") is not True:
        return False
    if metadata.get("mutation_allowed") is not False:
        return False
    if metadata.get("execution_allowed") is not False:
        return False
    if metadata.get("runtime_authority_granted") is not False:
        return False
    if metadata.get("canonical_runtime_success") is not False:
        return False
    if metadata.get("requires_governed_runtime_execution") is not True:
        return False
    if metadata.get("requires_sandbox_apply") is not True:
        return False
    if metadata.get("requires_rollback_checkpoint") is not True:
        return False
    if metadata.get("requires_verification_after_apply") is not True:
        return False

    if payload.get("dry_run_required") is not True:
        return False
    if payload.get("sandbox_required") is not True:
        return False
    if payload.get("rollback_checkpoint_required") is not True:
        return False
    if payload.get("verification_required") is not True:
        return False

    forbidden = {
        "runtime_evidence_id",
        "runtime_audit_metadata",
        "governed_mutation_lineage",
        "execution_summary",
        "canonical_success",
        "applied_patch",
        "files_written",
    }
    if forbidden.intersection(payload):
        return False

    return True


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
