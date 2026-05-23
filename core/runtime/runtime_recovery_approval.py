from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


APPROVAL_PENDING = "pending"
APPROVAL_APPROVE = "approve"
APPROVAL_REJECT = "reject"
APPROVAL_DEFER = "defer"
APPROVAL_SKIPPED = "skipped"


@dataclass(frozen=True)
class RuntimeRecoveryApproval:
    approval_required: bool
    approved: bool = False
    decision: str = APPROVAL_PENDING
    reason: str = ""
    approval_id: str | None = None
    recovery_id: str | None = None
    plan_id: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeRecoveryApprovalReport:
    ok: bool
    approval: RuntimeRecoveryApproval
    decision: str = APPROVAL_PENDING
    approved: bool = False
    approval_required: bool = False
    reason: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["approval"] = self.approval.to_dict()
        return payload


class RuntimeRecoveryApprovalEvaluator:
    def evaluate(
        self,
        plan: Any = None,
        *,
        recovery_id: str | None = None,
        approval_required: bool | None = None,
        approved: bool | None = None,
        reason: str | None = None,
        **kwargs: Any,
    ) -> RuntimeRecoveryApprovalReport:
        if approval_required is None:
            approval_required = bool(kwargs.get("requires_approval", False))

        if approved is None:
            approved = not bool(approval_required)

        if bool(approval_required) and not bool(approved):
            approval = require_runtime_recovery_approval(
                plan=plan,
                recovery_id=recovery_id,
                reason=reason,
            )
        else:
            approval = approve_runtime_recovery_plan(
                plan=plan,
                recovery_id=recovery_id,
                approved=bool(approved),
                approval_required=bool(approval_required),
                reason=reason,
            )

        return RuntimeRecoveryApprovalReport(
            ok=bool(approval.approved) or not bool(approval.approval_required),
            approval=approval,
            decision=approval.decision,
            approved=approval.approved,
            approval_required=approval.approval_required,
            reason=approval.reason,
            errors=[] if approval.approved or not approval.approval_required else ["runtime_recovery_approval_required"],
            warnings=[],
            metadata={
                "approval_id": approval.approval_id,
                "recovery_id": approval.recovery_id,
                "plan_id": approval.plan_id,
            },
        )

    def approve(
        self,
        plan: Any = None,
        *,
        recovery_id: str | None = None,
        reason: str | None = None,
        **kwargs: Any,
    ) -> RuntimeRecoveryApproval:
        return approve_runtime_recovery_plan(
            plan=plan,
            recovery_id=recovery_id,
            reason=reason,
            **kwargs,
        )

    def reject(
        self,
        plan: Any = None,
        *,
        recovery_id: str | None = None,
        reason: str | None = None,
        **kwargs: Any,
    ) -> RuntimeRecoveryApproval:
        return reject_runtime_recovery_plan(
            plan=plan,
            recovery_id=recovery_id,
            reason=reason,
            **kwargs,
        )

    def defer(
        self,
        plan: Any = None,
        *,
        recovery_id: str | None = None,
        reason: str | None = None,
        **kwargs: Any,
    ) -> RuntimeRecoveryApproval:
        return defer_runtime_recovery_plan(
            plan=plan,
            recovery_id=recovery_id,
            reason=reason,
            **kwargs,
        )


def _get_attr_or_key(source: Any, name: str, default: Any = None) -> Any:
    if source is None:
        return default

    if isinstance(source, dict):
        return source.get(name, default)

    return getattr(source, name, default)


def _extract_recovery_id(plan: Any = None, recovery_id: str | None = None) -> str | None:
    if recovery_id:
        return str(recovery_id)

    for key in ("recovery_id", "id", "plan_id"):
        value = _get_attr_or_key(plan, key, None)
        if value is not None and str(value).strip():
            return str(value).strip()

    return None


def _approval_id_for(recovery_id: str | None) -> str:
    if recovery_id:
        return f"runtime-recovery-approval:{recovery_id}"
    return "runtime-recovery-approval:unknown"


def approve_runtime_recovery_plan(
    plan: Any = None,
    *,
    recovery_id: str | None = None,
    approved: bool = True,
    approval_required: bool = False,
    reason: str | None = None,
    **_: Any,
) -> RuntimeRecoveryApproval:
    resolved_recovery_id = _extract_recovery_id(plan=plan, recovery_id=recovery_id)
    final_approved = bool(approved)

    return RuntimeRecoveryApproval(
        approval_required=bool(approval_required),
        approved=final_approved,
        decision=APPROVAL_APPROVE if final_approved else APPROVAL_REJECT,
        reason=str(reason or "runtime recovery plan approved by compatibility approval shim"),
        approval_id=_approval_id_for(resolved_recovery_id),
        recovery_id=resolved_recovery_id,
        plan_id=resolved_recovery_id,
    )


def reject_runtime_recovery_plan(
    plan: Any = None,
    *,
    recovery_id: str | None = None,
    reason: str | None = None,
    **_: Any,
) -> RuntimeRecoveryApproval:
    resolved_recovery_id = _extract_recovery_id(plan=plan, recovery_id=recovery_id)

    return RuntimeRecoveryApproval(
        approval_required=True,
        approved=False,
        decision=APPROVAL_REJECT,
        reason=str(reason or "runtime recovery plan rejected"),
        approval_id=_approval_id_for(resolved_recovery_id),
        recovery_id=resolved_recovery_id,
        plan_id=resolved_recovery_id,
    )


def defer_runtime_recovery_plan(
    plan: Any = None,
    *,
    recovery_id: str | None = None,
    reason: str | None = None,
    **_: Any,
) -> RuntimeRecoveryApproval:
    resolved_recovery_id = _extract_recovery_id(plan=plan, recovery_id=recovery_id)

    return RuntimeRecoveryApproval(
        approval_required=True,
        approved=False,
        decision=APPROVAL_DEFER,
        reason=str(reason or "runtime recovery approval deferred"),
        approval_id=_approval_id_for(resolved_recovery_id),
        recovery_id=resolved_recovery_id,
        plan_id=resolved_recovery_id,
    )


def require_runtime_recovery_approval(
    plan: Any = None,
    *,
    recovery_id: str | None = None,
    reason: str | None = None,
    **_: Any,
) -> RuntimeRecoveryApproval:
    resolved_recovery_id = _extract_recovery_id(plan=plan, recovery_id=recovery_id)

    return RuntimeRecoveryApproval(
        approval_required=True,
        approved=False,
        decision=APPROVAL_PENDING,
        reason=str(reason or "runtime recovery approval required"),
        approval_id=_approval_id_for(resolved_recovery_id),
        recovery_id=resolved_recovery_id,
        plan_id=resolved_recovery_id,
    )


def skip_runtime_recovery_approval(
    plan: Any = None,
    *,
    recovery_id: str | None = None,
    reason: str | None = None,
    **_: Any,
) -> RuntimeRecoveryApproval:
    resolved_recovery_id = _extract_recovery_id(plan=plan, recovery_id=recovery_id)

    return RuntimeRecoveryApproval(
        approval_required=False,
        approved=True,
        decision=APPROVAL_SKIPPED,
        reason=str(reason or "runtime recovery approval skipped"),
        approval_id=_approval_id_for(resolved_recovery_id),
        recovery_id=resolved_recovery_id,
        plan_id=resolved_recovery_id,
    )


def evaluate_runtime_recovery_approval(
    plan: Any = None,
    *,
    recovery_id: str | None = None,
    approval_required: bool | None = None,
    approved: bool | None = None,
    reason: str | None = None,
    **kwargs: Any,
) -> RuntimeRecoveryApprovalReport:
    return RuntimeRecoveryApprovalEvaluator().evaluate(
        plan=plan,
        recovery_id=recovery_id,
        approval_required=approval_required,
        approved=approved,
        reason=reason,
        **kwargs,
    )


def is_runtime_recovery_approved(approval: Any) -> bool:
    if isinstance(approval, RuntimeRecoveryApprovalReport):
        return bool(approval.approved)
    return bool(_get_attr_or_key(approval, "approved", False))


def runtime_recovery_approval_to_dict(approval: Any) -> Dict[str, Any]:
    if approval is None:
        return {}

    to_dict = getattr(approval, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, dict):
            return dict(payload)

    if isinstance(approval, dict):
        return dict(approval)

    return {
        "approval_required": bool(_get_attr_or_key(approval, "approval_required", False)),
        "approved": bool(_get_attr_or_key(approval, "approved", False)),
        "decision": str(_get_attr_or_key(approval, "decision", APPROVAL_PENDING)),
        "reason": str(_get_attr_or_key(approval, "reason", "")),
        "approval_id": _get_attr_or_key(approval, "approval_id", None),
        "recovery_id": _get_attr_or_key(approval, "recovery_id", None),
        "plan_id": _get_attr_or_key(approval, "plan_id", None),
    }


__all__ = [
    "APPROVAL_PENDING",
    "APPROVAL_APPROVE",
    "APPROVAL_REJECT",
    "APPROVAL_DEFER",
    "APPROVAL_SKIPPED",
    "RuntimeRecoveryApproval",
    "RuntimeRecoveryApprovalReport",
    "RuntimeRecoveryApprovalEvaluator",
    "approve_runtime_recovery_plan",
    "reject_runtime_recovery_plan",
    "defer_runtime_recovery_plan",
    "require_runtime_recovery_approval",
    "skip_runtime_recovery_approval",
    "evaluate_runtime_recovery_approval",
    "is_runtime_recovery_approved",
    "runtime_recovery_approval_to_dict",
]
