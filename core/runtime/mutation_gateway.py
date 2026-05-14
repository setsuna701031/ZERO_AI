from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.runtime.mutation_approval import MutationApprovalDecision
from core.runtime.mutation_runtime_pipeline import (
    MutationRuntimePipelineResult,
    run_mutation_runtime_pipeline,
)
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationRiskLevel,
    MutationScope,
    MutationVerificationRequirement,
    create_mutation_session,
)
from core.runtime.mutation_verification import MutationVerificationCheck


@dataclass(frozen=True)
class MutationGatewayRequest:
    intent: str
    initiator: str
    reason: str
    relative_paths: tuple[str, ...]
    scope: MutationScope
    workspace_root: str | Path
    sandbox_source_root: str | Path
    rollback_root: str | Path
    report_root: str | Path
    risk_level: MutationRiskLevel = MutationRiskLevel.MEDIUM
    approval_mode: MutationApprovalMode = MutationApprovalMode.REVIEW_REQUIRED
    verification: MutationVerificationRequirement = (
        MutationVerificationRequirement.TARGETED_TESTS
    )
    sandbox_run_id: str | None = None
    verification_checks: tuple[MutationVerificationCheck, ...] = ()
    approval_decisions: tuple[MutationApprovalDecision, ...] = ()
    dry_run: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


def run_governed_mutation(
    request: MutationGatewayRequest,
) -> MutationRuntimePipelineResult:
    """
    Single public gateway for governed mutation execution.

    Scheduler / repair_chain / self_edit_loop should call this gateway instead
    of importing mutation pipeline internals directly.
    """

    _validate_request(request)

    session = create_mutation_session(
        intent=request.intent,
        initiator=request.initiator,
        reason=request.reason,
        scope=request.scope,
        risk_level=request.risk_level,
        approval_mode=request.approval_mode,
        verification=request.verification,
        sandbox_run_id=request.sandbox_run_id,
        metadata=request.metadata,
    )

    return run_mutation_runtime_pipeline(
        session=session,
        relative_paths=list(request.relative_paths),
        workspace_root=request.workspace_root,
        sandbox_source_root=request.sandbox_source_root,
        rollback_root=request.rollback_root,
        report_root=request.report_root,
        verification_checks=list(request.verification_checks),
        approval_decisions=list(request.approval_decisions),
        dry_run=request.dry_run,
        metadata=request.metadata,
    )


def _validate_request(
    request: MutationGatewayRequest,
) -> None:
    if not request.relative_paths:
        raise ValueError("Mutation gateway request must include relative_paths.")

    if not str(request.intent).strip():
        raise ValueError("Mutation gateway request intent must be non-empty.")

    if not str(request.initiator).strip():
        raise ValueError("Mutation gateway request initiator must be non-empty.")

    if not str(request.reason).strip():
        raise ValueError("Mutation gateway request reason must be non-empty.")