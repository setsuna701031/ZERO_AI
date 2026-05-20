from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SandboxApplyDryRunResult:
    dry_run_id: str
    apply_request_id: str
    readiness_id: str
    repair_proposal_id: str
    verification_route_id: str
    sandbox_status: str
    target_files: tuple[str, ...]
    planned_operations: tuple[str, ...]
    rollback_checkpoint_draft: dict[str, Any]
    verification_draft: dict[str, Any]
    evidence_draft: dict[str, Any]
    blockers: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run_id": self.dry_run_id,
            "apply_request_id": self.apply_request_id,
            "readiness_id": self.readiness_id,
            "repair_proposal_id": self.repair_proposal_id,
            "verification_route_id": self.verification_route_id,
            "sandbox_status": self.sandbox_status,
            "target_files": list(self.target_files),
            "planned_operations": list(self.planned_operations),
            "rollback_checkpoint_draft": dict(self.rollback_checkpoint_draft),
            "verification_draft": dict(self.verification_draft),
            "evidence_draft": dict(self.evidence_draft),
            "blockers": list(self.blockers),
            "metadata": dict(self.metadata),
        }


def build_sandbox_apply_dry_run(
    apply_request: dict[str, Any],
    *,
    planned_operations: list[str] | tuple[str, ...] | None = None,
) -> SandboxApplyDryRunResult:
    """Build a dry-run sandbox apply result without mutating the repository.

    This function intentionally does not write files, run subprocesses, apply
    patches, or claim canonical runtime success. It only prepares the structural
    envelope needed before a future governed mutation executor can perform a real
    sandbox apply.
    """

    apply_request_id = str(apply_request.get("apply_request_id") or "").strip()
    readiness_id = str(apply_request.get("readiness_id") or "").strip()
    repair_proposal_id = str(apply_request.get("repair_proposal_id") or "").strip()
    verification_route_id = str(apply_request.get("verification_route_id") or "").strip()
    metadata = dict(apply_request.get("metadata") or {})

    if not apply_request_id:
        raise ValueError("apply_request_id_required")
    if not readiness_id:
        raise ValueError("readiness_id_required")
    if not repair_proposal_id:
        raise ValueError("repair_proposal_id_required")
    if not verification_route_id:
        raise ValueError("verification_route_id_required")

    if metadata.get("requires_governed_runtime_execution") is not True:
        raise ValueError("apply_request_must_require_governed_runtime_execution")
    if metadata.get("requires_sandbox_apply") is not True:
        raise ValueError("apply_request_must_require_sandbox_apply")
    if metadata.get("requires_rollback_checkpoint") is not True:
        raise ValueError("apply_request_must_require_rollback_checkpoint")
    if metadata.get("requires_verification_after_apply") is not True:
        raise ValueError("apply_request_must_require_verification_after_apply")
    if metadata.get("mutation_allowed") is not False:
        raise ValueError("apply_request_must_not_grant_mutation_authority")
    if metadata.get("execution_allowed") is not False:
        raise ValueError("apply_request_must_not_grant_execution_authority")

    if apply_request.get("dry_run_required") is not True:
        raise ValueError("dry_run_required")
    if apply_request.get("sandbox_required") is not True:
        raise ValueError("sandbox_required")
    if apply_request.get("rollback_checkpoint_required") is not True:
        raise ValueError("rollback_checkpoint_required")
    if apply_request.get("verification_required") is not True:
        raise ValueError("verification_required")

    target_files = tuple(
        str(item).strip()
        for item in (apply_request.get("target_files") or [])
        if str(item).strip()
    )
    clean_operations = tuple(
        str(item).strip()
        for item in (planned_operations or [])
        if str(item).strip()
    )

    blockers: list[str] = []
    if not target_files:
        blockers.append("target_files_required")
    if not clean_operations:
        blockers.append("planned_operations_required")

    sandbox_status = "blocked" if blockers else "dry_run_ready"

    rollback_checkpoint_draft = {
        "required": True,
        "checkpoint_type": "sandbox_snapshot_draft",
        "real_checkpoint_created": False,
    }
    verification_draft = {
        "required": True,
        "verification_route_id": verification_route_id,
        "real_verification_executed": False,
    }
    evidence_draft = {
        "required": True,
        "runtime_evidence_required": True,
        "audit_lineage_required": True,
        "real_runtime_evidence_created": False,
        "canonical_runtime_success": False,
    }

    payload = {
        "apply_request_id": apply_request_id,
        "readiness_id": readiness_id,
        "repair_proposal_id": repair_proposal_id,
        "verification_route_id": verification_route_id,
        "target_files": list(target_files),
        "planned_operations": list(clean_operations),
        "sandbox_status": sandbox_status,
        "blockers": blockers,
    }

    return SandboxApplyDryRunResult(
        dry_run_id="sandbox-apply-dry-run-" + _stable_hash(payload)[:16],
        apply_request_id=apply_request_id,
        readiness_id=readiness_id,
        repair_proposal_id=repair_proposal_id,
        verification_route_id=verification_route_id,
        sandbox_status=sandbox_status,
        target_files=target_files,
        planned_operations=clean_operations,
        rollback_checkpoint_draft=rollback_checkpoint_draft,
        verification_draft=verification_draft,
        evidence_draft=evidence_draft,
        blockers=tuple(blockers),
        metadata={
            "control_plane_only": True,
            "dry_run": True,
            "sandbox_only": True,
            "no_real_write": True,
            "mutation_allowed": False,
            "execution_allowed": False,
            "patch_apply_allowed": False,
            "runtime_authority_granted": False,
            "canonical_runtime_success": False,
            "requires_governed_runtime_execution_for_real_apply": True,
            "requires_real_rollback_checkpoint_before_commit": True,
            "requires_real_verification_before_success": True,
            "requires_runtime_evidence_after_execution": True,
            "requires_audit_lineage_after_execution": True,
            "source_apply_request_metadata": metadata,
        },
    )


def validate_sandbox_apply_dry_run_contract(payload: dict[str, Any]) -> bool:
    required = {
        "dry_run_id",
        "apply_request_id",
        "readiness_id",
        "repair_proposal_id",
        "verification_route_id",
        "sandbox_status",
        "target_files",
        "planned_operations",
        "rollback_checkpoint_draft",
        "verification_draft",
        "evidence_draft",
        "blockers",
        "metadata",
    }
    if not required.issubset(payload):
        return False

    metadata = payload.get("metadata") or {}
    if metadata.get("dry_run") is not True:
        return False
    if metadata.get("sandbox_only") is not True:
        return False
    if metadata.get("no_real_write") is not True:
        return False
    if metadata.get("mutation_allowed") is not False:
        return False
    if metadata.get("execution_allowed") is not False:
        return False
    if metadata.get("runtime_authority_granted") is not False:
        return False
    if metadata.get("canonical_runtime_success") is not False:
        return False

    evidence_draft = payload.get("evidence_draft") or {}
    if evidence_draft.get("real_runtime_evidence_created") is not False:
        return False
    if evidence_draft.get("canonical_runtime_success") is not False:
        return False

    rollback_draft = payload.get("rollback_checkpoint_draft") or {}
    if rollback_draft.get("real_checkpoint_created") is not False:
        return False

    verification_draft = payload.get("verification_draft") or {}
    if verification_draft.get("real_verification_executed") is not False:
        return False

    forbidden = {
        "runtime_evidence_id",
        "runtime_audit_metadata",
        "governed_mutation_lineage",
        "execution_summary",
        "canonical_success",
        "applied_patch",
        "files_written",
        "subprocess_result",
    }
    if forbidden.intersection(payload):
        return False

    return True


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
