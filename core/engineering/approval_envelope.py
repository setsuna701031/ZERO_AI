from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from core.engineering.diff_proposal import DiffProposal


@dataclass(frozen=True)
class ApprovalEnvelope:
    approval_id: str
    proposal_id: str
    plan_id: str
    task: str
    review_state: str
    reviewer: str
    authority_scope: str
    verification_profile_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "proposal_id": self.proposal_id,
            "plan_id": self.plan_id,
            "task": self.task,
            "review_state": self.review_state,
            "reviewer": self.reviewer,
            "authority_scope": self.authority_scope,
            "verification_profile_id": self.verification_profile_id,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class VerificationCommand:
    command: str
    reason: str
    scope: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "reason": self.reason,
            "scope": self.scope,
        }


@dataclass(frozen=True)
class VerificationProfile:
    verification_profile_id: str
    proposal_id: str
    plan_id: str
    commands: tuple[VerificationCommand, ...]
    retry_budget: int
    rollback_required: bool
    recovery_required: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verification_profile_id": self.verification_profile_id,
            "proposal_id": self.proposal_id,
            "plan_id": self.plan_id,
            "commands": [item.to_dict() for item in self.commands],
            "retry_budget": self.retry_budget,
            "rollback_required": self.rollback_required,
            "recovery_required": self.recovery_required,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class GovernedApplyEligibility:
    eligibility_id: str
    proposal_id: str
    plan_id: str
    approval_id: str
    verification_profile_id: str
    status: str
    reasons: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligibility_id": self.eligibility_id,
            "proposal_id": self.proposal_id,
            "plan_id": self.plan_id,
            "approval_id": self.approval_id,
            "verification_profile_id": self.verification_profile_id,
            "status": self.status,
            "reasons": list(self.reasons),
            "metadata": dict(self.metadata),
        }


def build_verification_profile(
    proposal: DiffProposal,
    *,
    retry_budget: int = 1,
) -> VerificationProfile:
    payload = proposal.to_dict()
    classifications = {
        str(item.get("classification", "other"))
        for item in payload.get("files", [])
    }

    commands: list[VerificationCommand] = [
        VerificationCommand(
            command="python -m compileall core/runtime core/tasks core/engineering",
            reason="baseline syntax validation for governed engineering surfaces",
            scope="compile",
        )
    ]

    if "test" in classifications or "source" in classifications:
        commands.append(
            VerificationCommand(
                command=(
                    "python -m pytest "
                    "tests/test_runtime_mainline_freeze_contract.py "
                    "tests/test_runtime_topology_freeze_gate.py"
                ),
                reason="preserve sealed runtime kernel invariants",
                scope="runtime_freeze",
            )
        )

    if "docs" in classifications:
        commands.append(
            VerificationCommand(
                command="python -m pytest tests/test_interactive_engineering_loop_contract.py",
                reason="preserve engineering workflow contract after documentation updates",
                scope="workflow_contract",
            )
        )

    if len(commands) == 1:
        commands.append(
            VerificationCommand(
                command="python -m pytest tests/test_repo_scan_impacted_plan_contract.py",
                reason="preserve read-only planning contract",
                scope="planning_contract",
            )
        )

    profile_payload = {
        "proposal_id": proposal.proposal_id,
        "plan_id": proposal.plan_id,
        "commands": [item.to_dict() for item in commands],
        "retry_budget": int(retry_budget),
    }

    return VerificationProfile(
        verification_profile_id="verification-profile-" + _stable_hash(profile_payload)[:16],
        proposal_id=proposal.proposal_id,
        plan_id=proposal.plan_id,
        commands=tuple(commands),
        retry_budget=max(0, int(retry_budget)),
        rollback_required=True,
        recovery_required=True,
        metadata={
            "read_only": True,
            "mutation_allowed": False,
            "execution_allowed": False,
            "verification_execution_allowed": False,
            "approval_required": True,
            "governed_apply_required": True,
        },
    )


def build_approval_envelope(
    proposal: DiffProposal,
    *,
    reviewer: str = "human",
    review_state: str = "pending",
    authority_scope: str = "proposal_review_only",
    verification_profile: VerificationProfile | None = None,
) -> ApprovalEnvelope:
    normalized_state = str(review_state or "").strip().lower()
    if normalized_state not in {"pending", "approved", "rejected"}:
        raise ValueError(f"unsupported_review_state:{review_state}")

    payload = {
        "proposal_id": proposal.proposal_id,
        "plan_id": proposal.plan_id,
        "task": proposal.task,
        "review_state": normalized_state,
        "reviewer": reviewer,
        "authority_scope": authority_scope,
        "verification_profile_id": (
            verification_profile.verification_profile_id
            if verification_profile is not None
            else None
        ),
    }

    return ApprovalEnvelope(
        approval_id="approval-envelope-" + _stable_hash(payload)[:16],
        proposal_id=proposal.proposal_id,
        plan_id=proposal.plan_id,
        task=proposal.task,
        review_state=normalized_state,
        reviewer=reviewer,
        authority_scope=authority_scope,
        verification_profile_id=(
            verification_profile.verification_profile_id
            if verification_profile is not None
            else None
        ),
        metadata={
            "read_only": True,
            "mutation_allowed": False,
            "execution_allowed": False,
            "patch_apply_allowed": False,
            "approval_envelope_only": True,
            "governed_apply_required": True,
        },
    )


def build_governed_apply_eligibility(
    *,
    proposal: DiffProposal,
    approval: ApprovalEnvelope,
    verification_profile: VerificationProfile,
) -> GovernedApplyEligibility:
    reasons: list[str] = []

    if approval.proposal_id != proposal.proposal_id:
        reasons.append("approval proposal id mismatch")
    if verification_profile.proposal_id != proposal.proposal_id:
        reasons.append("verification profile proposal id mismatch")
    if approval.review_state != "approved":
        reasons.append("approval is not approved")
    if not verification_profile.commands:
        reasons.append("verification profile has no commands")
    if verification_profile.rollback_required is not True:
        reasons.append("rollback requirement missing")
    if verification_profile.recovery_required is not True:
        reasons.append("recovery requirement missing")

    status = "eligible_for_governed_apply" if not reasons else "blocked"

    payload = {
        "proposal_id": proposal.proposal_id,
        "plan_id": proposal.plan_id,
        "approval_id": approval.approval_id,
        "verification_profile_id": verification_profile.verification_profile_id,
        "status": status,
        "reasons": reasons,
    }

    return GovernedApplyEligibility(
        eligibility_id="governed-apply-eligibility-" + _stable_hash(payload)[:16],
        proposal_id=proposal.proposal_id,
        plan_id=proposal.plan_id,
        approval_id=approval.approval_id,
        verification_profile_id=verification_profile.verification_profile_id,
        status=status,
        reasons=tuple(reasons),
        metadata={
            "read_only": True,
            "mutation_allowed": False,
            "execution_allowed": False,
            "patch_apply_allowed": False,
            "eligibility_only": True,
            "requires_governed_runtime": True,
        },
    )


def validate_approval_envelope_contract(payload: dict[str, Any]) -> bool:
    required = {
        "approval_id",
        "proposal_id",
        "plan_id",
        "task",
        "review_state",
        "reviewer",
        "authority_scope",
        "metadata",
    }
    if not required.issubset(payload):
        return False

    metadata = payload.get("metadata") or {}
    if metadata.get("mutation_allowed") is not False:
        return False
    if metadata.get("execution_allowed") is not False:
        return False
    if metadata.get("governed_apply_required") is not True:
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
    return not forbidden_success_fields.intersection(payload)


def validate_verification_profile_contract(payload: dict[str, Any]) -> bool:
    required = {
        "verification_profile_id",
        "proposal_id",
        "plan_id",
        "commands",
        "retry_budget",
        "rollback_required",
        "recovery_required",
        "metadata",
    }
    if not required.issubset(payload):
        return False

    metadata = payload.get("metadata") or {}
    if metadata.get("mutation_allowed") is not False:
        return False
    if metadata.get("execution_allowed") is not False:
        return False
    if metadata.get("verification_execution_allowed") is not False:
        return False
    if payload.get("rollback_required") is not True:
        return False
    if payload.get("recovery_required") is not True:
        return False
    return bool(payload.get("commands"))


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
