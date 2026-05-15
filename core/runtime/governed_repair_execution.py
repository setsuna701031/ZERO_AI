from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

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
from core.runtime.runtime_recovery_gate_hook import runtime_recovery_gate_hook
from core.tasks.runtime_repair_apply_transaction import (
    build_runtime_repair_apply_plan,
    preflight_runtime_repair_apply_transaction,
)

GovernedRepairGateHook = Callable[[dict[str, Any]], Any]


def _is_blocking_gate_result(result: Any) -> bool:
    if result is None:
        return False
    if isinstance(result, bool):
        return not result
    if isinstance(result, dict):
        if result.get("ok") is False:
            return True
        if result.get("blocked") is True:
            return True
        if result.get("status") in {"blocked", "rejected", "failed"}:
            return True
    return False


def _gate_error_message(result: Any) -> str:
    if isinstance(result, dict):
        for key in ("error", "reason", "message", "summary"):
            value = result.get(key)
            if value:
                return str(value)
        blockers = result.get("blockers")
        if blockers:
            return ", ".join(str(item) for item in blockers)
    return str(result)


def _resolve_gate_hook(
    gate_hook: GovernedRepairGateHook | None,
    *,
    use_runtime_recovery_gate: bool,
) -> GovernedRepairGateHook | None:
    if gate_hook is not None:
        return gate_hook
    if use_runtime_recovery_gate:
        return runtime_recovery_gate_hook
    return None


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
    gate_hook: GovernedRepairGateHook | None = None,
    use_runtime_recovery_gate: bool = False,
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

    resolved_gate_hook = _resolve_gate_hook(
        gate_hook,
        use_runtime_recovery_gate=use_runtime_recovery_gate,
    )

    if resolved_gate_hook is not None:
        gate_result = resolved_gate_hook(
            {
                "transaction": transaction,
                "preflight": preflight,
                "apply_plan": apply_plan,
                "request": request,
            }
        )
        if _is_blocking_gate_result(gate_result):
            raise ValueError(
                "governed_repair_gate_blocked: "
                + _gate_error_message(gate_result)
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
