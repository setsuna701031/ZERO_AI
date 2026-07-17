from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


APPROVAL_PENDING = "pending"
APPROVAL_APPROVE = "approve"
APPROVAL_REJECT = "reject"
APPROVAL_DEFER = "defer"
APPROVAL_SKIPPED = "skipped"
RECOVERY_PLAN_APPROVAL_GRANTED = "recovery_plan_approval_granted"

_RECOVERY_PLAN_APPROVAL_GRANTED_ALIASES = {
    "recovery_approval_granted",
    "find_recovery_approval_granted",
    RECOVERY_PLAN_APPROVAL_GRANTED,
}


def canonicalize_runtime_recovery_approval_reason(reason: Any, *, gate: str = "") -> str:
    text = "" if reason is None else str(reason)
    if gate == "recovery" and text in _RECOVERY_PLAN_APPROVAL_GRANTED_ALIASES:
        return RECOVERY_PLAN_APPROVAL_GRANTED
    if text in _RECOVERY_PLAN_APPROVAL_GRANTED_ALIASES:
        return RECOVERY_PLAN_APPROVAL_GRANTED
    return text


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
        payload = _build_recovery_approval_payload(
            plan,
            recovery_id=recovery_id,
            approval_required=approval_required,
            approved=approved,
            reason=reason,
            requires_approval=kwargs.get("requires_approval", False),
        )
        return RuntimeRecoveryApprovalReport(payload)

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
        reason=canonicalize_runtime_recovery_approval_reason(
            reason or RECOVERY_PLAN_APPROVAL_GRANTED,
            gate="recovery",
        ),
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


class RuntimeRecoveryApprovalReportCompat:
    SCHEMA = "zero.runtime.recovery_approval.compat.v1"

    def __init__(self, payload: Any = None, **kwargs: Any) -> None:
        if isinstance(payload, dict) and not kwargs:
            normalized = copy.deepcopy(payload)
        else:
            normalized = self._payload_from_kwargs(payload, kwargs)
        normalized.setdefault("schema", self.SCHEMA)
        normalized.setdefault("read_only", True)
        normalized.setdefault("recovery_approval", self._default_gate("recovery"))
        normalized.setdefault("replay_approval", self._default_gate("replay"))
        normalized.setdefault("rollback_approval", self._default_gate("rollback"))
        normalized.setdefault("failed_execution_approval", self._default_gate("failed_execution"))
        normalized.setdefault("consistency_check", {"state": APPROVAL_APPROVE, "issues": []})
        normalized.setdefault("approval_reasons", [])
        self._canonicalize_recovery_approval_reasons(normalized)
        normalized["fingerprint"] = _stable_approval_fingerprint(
            {key: value for key, value in normalized.items() if key != "fingerprint"}
        )
        self._payload = self._json_safe(normalized)

    @property
    def payload(self) -> Dict[str, Any]:
        return copy.deepcopy(self._payload)

    @property
    def fingerprint(self) -> str:
        return str(self._payload.get("fingerprint") or "")

    def to_dict(self) -> Dict[str, Any]:
        return self.payload

    def consistency_check(self) -> Dict[str, Any]:
        return copy.deepcopy(self._payload.get("consistency_check", {}))

    def recovery_approval(self) -> Dict[str, Any]:
        return copy.deepcopy(self._payload.get("recovery_approval", {}))

    def replay_approval(self) -> Dict[str, Any]:
        return copy.deepcopy(self._payload.get("replay_approval", {}))

    def rollback_approval(self) -> Dict[str, Any]:
        return copy.deepcopy(self._payload.get("rollback_approval", {}))

    def failed_execution_approval(self) -> Dict[str, Any]:
        return copy.deepcopy(self._payload.get("failed_execution_approval", {}))

    def approval_reasons(self) -> List[Dict[str, Any]]:
        return copy.deepcopy(self._payload.get("approval_reasons", []))

    def _payload_from_kwargs(self, approval: Any, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        approval_payload = approval.to_dict() if hasattr(approval, "to_dict") else {}
        return {
            "ok": bool(kwargs.get("ok", False)),
            "approval": copy.deepcopy(approval_payload),
            "decision": str(kwargs.get("decision") or approval_payload.get("decision") or APPROVAL_PENDING),
            "approved": bool(kwargs.get("approved", approval_payload.get("approved", False))),
            "approval_required": bool(
                kwargs.get("approval_required", approval_payload.get("approval_required", False))
            ),
            "reason": str(kwargs.get("reason") or approval_payload.get("reason") or ""),
            "errors": copy.deepcopy(kwargs.get("errors", [])),
            "warnings": copy.deepcopy(kwargs.get("warnings", [])),
            "metadata": copy.deepcopy(kwargs.get("metadata", {})),
        }

    def _default_gate(self, gate: str) -> Dict[str, Any]:
        return {
            "gate": gate,
            "state": APPROVAL_DEFER,
            "reason": "approval report did not include gate decision",
            "approval_can_be_granted": False,
            "action": "none",
            "executes_action": False,
        }

    def _json_safe(self, payload: Any) -> Dict[str, Any]:
        encoded = json.dumps(payload if isinstance(payload, dict) else {}, default=str, sort_keys=True)
        return json.loads(encoded)

    def _canonicalize_recovery_approval_reasons(self, payload: Dict[str, Any]) -> None:
        for key in ("reason", "approval_reason"):
            if key in payload:
                payload[key] = canonicalize_runtime_recovery_approval_reason(payload.get(key))
        approval = payload.get("approval")
        if isinstance(approval, dict):
            for key in ("reason", "approval_reason"):
                if key in approval:
                    approval[key] = canonicalize_runtime_recovery_approval_reason(approval.get(key))
        gate = payload.get("recovery_approval")
        if isinstance(gate, dict) and "reason" in gate:
            gate["reason"] = canonicalize_runtime_recovery_approval_reason(
                gate.get("reason"),
                gate="recovery",
            )
        reasons = payload.get("approval_reasons")
        if isinstance(reasons, list):
            for reason in reasons:
                if isinstance(reason, dict) and self._json_safe_gate(reason.get("gate")) == "recovery":
                    reason["reason"] = canonicalize_runtime_recovery_approval_reason(
                        reason.get("reason"),
                        gate="recovery",
                    )

    def _json_safe_gate(self, value: Any) -> str:
        return "" if value is None else str(value)


RuntimeRecoveryApprovalReport = RuntimeRecoveryApprovalReportCompat


def _build_recovery_approval_payload(
    plan: Any,
    *,
    recovery_id: str | None = None,
    approval_required: bool | None = None,
    approved: bool | None = None,
    reason: str | None = None,
    requires_approval: bool = False,
) -> Dict[str, Any]:
    plan_payload = _plan_payload(plan)
    isolation_plans = _safe_list(plan_payload.get("lineage_isolation_plans"))
    rollback_plans = _safe_list(plan_payload.get("rollback_plans"))
    replay_plans = _safe_list(plan_payload.get("replay_reconstruction_plans"))
    failed_plans = _safe_list(plan_payload.get("failed_execution_plans"))

    issues: List[Dict[str, Any]] = []
    if any(item.get("policy_decision") == "block" for item in rollback_plans if isinstance(item, dict)):
        issues.append({"type": "policy_plan_decision_mismatch", "gate": "rollback"})

    deferred_policy_decisions = {
        str(item.get("policy_decision") or "").strip().lower()
        for item in (rollback_plans + replay_plans + failed_plans)
        if isinstance(item, dict)
    }.intersection({"warn", "defer", "deferred", "review_required", "pending"})
    missing_evidence = any(
        item.get("classification") == "missing_evidence_isolation_plan"
        for item in isolation_plans
        if isinstance(item, dict)
    )
    unsafe_lineage = bool(isolation_plans)
    rejected = bool(unsafe_lineage or issues)
    deferred = bool(
        (requires_approval or approval_required or deferred_policy_decisions)
        and approved is not True
        and not rejected
    )

    if rejected:
        state = APPROVAL_REJECT
        recovery_reason = "unsafe_recovery_isolated_lineage" if unsafe_lineage else "policy_plan_decision_mismatch"
        can_grant = False
    elif deferred:
        state = APPROVAL_DEFER
        recovery_reason = str(
            reason
            or (
                "policy_warning_requires_review"
                if deferred_policy_decisions
                else "runtime_recovery_approval_required"
            )
        )
        can_grant = False
    else:
        state = APPROVAL_APPROVE
        recovery_reason = canonicalize_runtime_recovery_approval_reason(
            reason or RECOVERY_PLAN_APPROVAL_GRANTED,
            gate="recovery",
        )
        can_grant = True

    consistency = {
        "state": APPROVAL_REJECT if issues else APPROVAL_APPROVE,
        "issues": copy.deepcopy(issues),
    }
    gates = {
        "recovery_approval": _approval_gate("recovery", state, recovery_reason, can_grant),
        "replay_approval": _approval_gate(
            "replay",
            state,
            "replay_approval_granted" if state == APPROVAL_APPROVE else recovery_reason,
            can_grant,
            plan_count=len(replay_plans),
        ),
        "rollback_approval": _approval_gate(
            "rollback",
            state,
            "rollback_approval_granted" if state == APPROVAL_APPROVE else recovery_reason,
            can_grant,
            plan_count=len(rollback_plans),
        ),
        "failed_execution_approval": _approval_gate(
            "failed_execution",
            state,
            "failed_execution_approval_granted" if state == APPROVAL_APPROVE else recovery_reason,
            can_grant,
            plan_count=len(failed_plans),
        ),
    }
    payload = {
        "ok": state == APPROVAL_APPROVE,
        "schema": RuntimeRecoveryApprovalReportCompat.SCHEMA,
        "read_only": True,
        "source_plan_fingerprint": str(getattr(plan, "fingerprint", "")),
        "approval_state": state,
        "approved": state == APPROVAL_APPROVE,
        "approval_required": state != APPROVAL_APPROVE,
        "decision": state,
        "reason": recovery_reason,
        "consistency_check": consistency,
        **gates,
        "approval_reasons": [
            {"gate": key.replace("_approval", ""), "state": value["state"], "reason": value["reason"]}
            for key, value in gates.items()
        ],
        "approval": {
            "approval_required": state != APPROVAL_APPROVE,
            "approved": state == APPROVAL_APPROVE,
            "decision": state,
            "reason": recovery_reason,
            "approval_id": _approval_id_for(recovery_id or plan_payload.get("plan_id")),
            "recovery_id": recovery_id or plan_payload.get("recovery_id"),
            "plan_id": plan_payload.get("plan_id"),
        },
        "missing_evidence": missing_evidence,
    }
    return payload


def _approval_gate(
    gate: str,
    state: str,
    reason: str,
    can_grant: bool,
    *,
    plan_count: int = 0,
) -> Dict[str, Any]:
    reason = canonicalize_runtime_recovery_approval_reason(reason, gate=gate)
    return {
        "gate": gate,
        "state": state,
        "reason": reason,
        "approval_can_be_granted": bool(can_grant),
        "approved": state == APPROVAL_APPROVE,
        "approval_required": state != APPROVAL_APPROVE,
        "plan_count": int(plan_count),
        "action": "none",
        "executes_action": False,
    }


def _plan_payload(plan: Any) -> Dict[str, Any]:
    if plan is None:
        return {}
    payload = getattr(plan, "payload", None)
    if isinstance(payload, dict):
        return copy.deepcopy(payload)
    to_dict = getattr(plan, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
        if isinstance(value, dict):
            return copy.deepcopy(value)
    if isinstance(plan, dict):
        return copy.deepcopy(plan)
    return {}


def _safe_list(value: Any) -> List[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


def _stable_approval_fingerprint(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "APPROVAL_PENDING",
    "APPROVAL_APPROVE",
    "APPROVAL_REJECT",
    "APPROVAL_DEFER",
    "APPROVAL_SKIPPED",
    "RECOVERY_PLAN_APPROVAL_GRANTED",
    "RuntimeRecoveryApproval",
    "RuntimeRecoveryApprovalReport",
    "RuntimeRecoveryApprovalEvaluator",
    "canonicalize_runtime_recovery_approval_reason",
    "approve_runtime_recovery_plan",
    "reject_runtime_recovery_plan",
    "defer_runtime_recovery_plan",
    "require_runtime_recovery_approval",
    "skip_runtime_recovery_approval",
    "evaluate_runtime_recovery_approval",
    "is_runtime_recovery_approved",
    "runtime_recovery_approval_to_dict",
]
