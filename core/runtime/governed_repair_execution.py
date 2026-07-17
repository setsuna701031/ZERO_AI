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

try:
    from core.runtime.runtime_legality import RuntimeLegalityEngine
except Exception:  # pragma: no cover - compatibility during partial runtime imports
    RuntimeLegalityEngine = None  # type: ignore[assignment]


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


def _risk_level_text(value: Any) -> str:
    if isinstance(value, MutationRiskLevel):
        return str(getattr(value, "value", value.name)).lower()
    return str(value or "unknown").strip().lower() or "unknown"


def _decision_to_dict(decision: Any) -> dict[str, Any]:
    if decision is None:
        return {}

    to_dict = getattr(decision, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, dict):
            return dict(payload)

    payload: dict[str, Any] = {}
    for key in (
        "allowed",
        "requires_review",
        "blocked",
        "decision",
        "reason",
        "violated_rules",
        "action_type",
        "risk_level",
        "governance_id",
        "constitution_version",
    ):
        if hasattr(decision, key):
            payload[key] = getattr(decision, key)

    if "decision" not in payload:
        if bool(payload.get("blocked")):
            payload["decision"] = "BLOCK"
        elif bool(payload.get("requires_review")):
            payload["decision"] = "REVIEW"
        elif bool(payload.get("allowed")):
            payload["decision"] = "ALLOW"
        else:
            payload["decision"] = "UNKNOWN"

    return payload


def _enforce_runtime_legality(
    *,
    action_type: str,
    risk_level: Any,
    governance_snapshot: Any,
    constitution: Any,
) -> None:
    if constitution is None or RuntimeLegalityEngine is None:
        return

    decision = RuntimeLegalityEngine().evaluate_action(
        action_type=action_type,
        risk_level=_risk_level_text(risk_level),
        governance_snapshot=governance_snapshot,
        constitution=constitution,
    )

    if not (
        bool(getattr(decision, "blocked", False))
        or bool(getattr(decision, "requires_review", False))
    ):
        return

    payload = _decision_to_dict(decision)
    decision_name = str(payload.get("decision") or "UNKNOWN").upper()

    if decision_name == "BLOCK":
        raise PermissionError(
            "governed_runtime_execution_blocked: "
            + str(payload.get("reason") or "runtime legality blocked execution")
        )

    raise PermissionError(
        "governed_runtime_execution_requires_review: "
        + str(payload.get("reason") or "runtime legality requires review")
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
    gate_hook: GovernedRepairGateHook | None = None,
    use_runtime_recovery_gate: bool = False,
    governance_snapshot: Any = None,
    constitution: Any = None,
    enforce_legality: bool = True,
    legality_action_type: str = "governed_repair_transaction",
) -> MutationRuntimePipelineResult:
    if enforce_legality:
        _enforce_runtime_legality(
            action_type=legality_action_type,
            risk_level=risk_level,
            governance_snapshot=governance_snapshot,
            constitution=constitution,
        )

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
