from __future__ import annotations

from pathlib import Path
from typing import Any

from core.runtime.mutation_runtime_pipeline import MutationRuntimePipelineResult
from core.runtime.repair_transaction_gateway_adapter import (
    build_gateway_request_from_repair_transaction,
    run_governed_repair_transaction,
)
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationRiskLevel,
    MutationVerificationRequirement,
)
from core.tasks.runtime_repair_apply_transaction import (
    build_runtime_repair_apply_plan,
    preflight_runtime_repair_apply_transaction,
)


def execute_governed_repair_transaction(
    transaction: Any,
    *,
    workspace_root: str | Path,
    sandbox_source_root: str | Path,
    rollback_root: str | Path,
    report_root: str | Path,
    allowed_roots: list[str] | tuple[str, ...],
    initiator: str = "governed_repair_execution",
    intent: str = "governed runtime repair execution",
    reason: str = "execute staged repair transaction through governed mutation topology",
    risk_level: MutationRiskLevel = MutationRiskLevel.MEDIUM,
    approval_mode: MutationApprovalMode = MutationApprovalMode.REVIEW_REQUIRED,
    verification: MutationVerificationRequirement = MutationVerificationRequirement.TARGETED_TESTS,
    dry_run: bool | None = None,
) -> MutationRuntimePipelineResult:
    preflight = preflight_runtime_repair_apply_transaction(
        transaction,
        workspace_root=workspace_root,
        allowed_roots=list(allowed_roots),
    )

    if not preflight.get("ok", False):
        blockers = preflight.get("blockers") or []
        raise ValueError(
            "repair_transaction_preflight_failed: "
            + ", ".join(str(item) for item in blockers)
        )

    apply_plan = build_runtime_repair_apply_plan(transaction)

    if not apply_plan.get("ready", False):
        warnings = apply_plan.get("warnings") or []
        raise ValueError(
            "repair_apply_plan_not_ready: "
            + ", ".join(str(item) for item in warnings)
        )

    request = build_gateway_request_from_repair_transaction(
        transaction,
        workspace_root=workspace_root,
        sandbox_source_root=sandbox_source_root,
        rollback_root=rollback_root,
        report_root=report_root,
        initiator=initiator,
        intent=intent,
        reason=reason,
        allowed_paths=tuple(allowed_roots),
        risk_level=risk_level,
        approval_mode=approval_mode,
        verification=verification,
        dry_run=dry_run,
    )

    return run_governed_repair_transaction(
        transaction,
        workspace_root=workspace_root,
        sandbox_source_root=sandbox_source_root,
        rollback_root=rollback_root,
        report_root=report_root,
        initiator=request.initiator,
        intent=request.intent,
        reason=request.reason,
        allowed_paths=request.scope.allowed_paths,
        denied_paths=request.scope.denied_paths,
        risk_level=request.risk_level,
        approval_mode=request.approval_mode,
        verification=request.verification,
        dry_run=request.dry_run,
    )