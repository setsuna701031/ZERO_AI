from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from core.engineering.repo_scan import ImpactedFilePlan


@dataclass(frozen=True)
class DiffProposalFile:
    path: str
    classification: str
    proposal_reason: str
    proposed_operation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "classification": self.classification,
            "proposal_reason": self.proposal_reason,
            "proposed_operation": self.proposed_operation,
        }


@dataclass(frozen=True)
class DiffProposal:
    proposal_id: str
    plan_id: str
    task: str
    files: tuple[DiffProposalFile, ...]
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "plan_id": self.plan_id,
            "task": self.task,
            "files": [item.to_dict() for item in self.files],
            "summary": self.summary,
            "metadata": dict(self.metadata),
        }


DEFAULT_OPERATION_BY_CLASSIFICATION = {
    "source": "propose_source_change",
    "test": "propose_test_update",
    "docs": "propose_documentation_update",
    "config": "propose_configuration_review",
    "other": "propose_manual_review",
}


def build_diff_proposal(
    plan: ImpactedFilePlan,
    *,
    summary: str | None = None,
) -> DiffProposal:
    payload_files: list[DiffProposalFile] = []

    for item in plan.files:
        operation = DEFAULT_OPERATION_BY_CLASSIFICATION.get(
            item.classification,
            "propose_manual_review",
        )
        payload_files.append(
            DiffProposalFile(
                path=item.path,
                classification=item.classification,
                proposal_reason="; ".join(item.reasons),
                proposed_operation=operation,
            )
        )

    proposal_summary = summary or (
        f"Read-only diff proposal for impacted plan {plan.plan_id}"
    )

    payload = {
        "plan_id": plan.plan_id,
        "task": plan.task,
        "files": [item.to_dict() for item in payload_files],
        "summary": proposal_summary,
    }

    return DiffProposal(
        proposal_id="diff-proposal-" + _stable_hash(payload)[:16],
        plan_id=plan.plan_id,
        task=plan.task,
        files=tuple(payload_files),
        summary=proposal_summary,
        metadata={
            "read_only": True,
            "mutation_allowed": False,
            "execution_allowed": False,
            "patch_apply_allowed": False,
            "approval_required": True,
            "governed_runtime_required": True,
            "proposal_only": True,
        },
    )


def validate_diff_proposal_contract(payload: dict[str, Any]) -> bool:
    required_fields = {
        "proposal_id",
        "plan_id",
        "task",
        "files",
        "summary",
        "metadata",
    }

    if not required_fields.issubset(payload):
        return False

    metadata = payload.get("metadata") or {}

    if metadata.get("mutation_allowed") is not False:
        return False

    if metadata.get("execution_allowed") is not False:
        return False

    if metadata.get("approval_required") is not True:
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


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
