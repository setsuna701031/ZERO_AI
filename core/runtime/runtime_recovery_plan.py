from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


RECOVERY_STATUS_PLANNED = "planned"
RECOVERY_STATUS_ROLLBACK_REQUIRED = "rollback_required"
RECOVERY_STATUS_UNRECOVERABLE = "unrecoverable"

ROLLBACK_REQUIRING_FAILURE_TYPES = {
    "mutation_failed",
    "patch_apply_failed",
    "transaction_failed",
    "seal_mismatch",
    "integrity_mismatch",
    "unsafe_mutation",
    "partial_apply",
    "write_failure",
}

UNRECOVERABLE_FAILURE_TYPES = {
    "approval_denied",
    "unsafe_action_blocked",
    "policy_blocked",
    "scope_violation",
}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_recovery_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _copy_dict(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _copy_list(value: Any) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


def _string(value: Any, default: str = "") -> str:
    text = str(value if value is not None else default).strip()
    return text or default


@dataclass(frozen=True)
class RuntimeRecoveryFailure:
    failure_type: str
    message: str = ""
    source: str = "runtime"
    status: str = "failed"
    source_session_id: str = ""
    task_id: str = ""
    step_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    observed_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_type": self.failure_type,
            "message": self.message,
            "source": self.source,
            "status": self.status,
            "source_session_id": self.source_session_id,
            "task_id": self.task_id,
            "step_id": self.step_id,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "observed_at": self.observed_at,
        }


@dataclass(frozen=True)
class RuntimeRecoveryAction:
    action_id: str
    action_type: str
    reason: str
    required: bool = True
    payload: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "reason": self.reason,
            "required": self.required,
            "payload": copy.deepcopy(self.payload),
            "status": self.status,
        }


@dataclass(frozen=True)
class RuntimeRecoveryPlan:
    plan_id: str
    recovery_id: str
    source_session_id: str
    source_failure: RuntimeRecoveryFailure
    status: str
    rollback_required: bool
    replay_required: bool
    verification_required: bool
    actions: list[RuntimeRecoveryAction] = field(default_factory=list)
    replay_reference: dict[str, Any] = field(default_factory=dict)
    rollback_reference: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "recovery_id": self.recovery_id,
            "source_session_id": self.source_session_id,
            "source_failure": self.source_failure.to_dict(),
            "status": self.status,
            "rollback_required": self.rollback_required,
            "replay_required": self.replay_required,
            "verification_required": self.verification_required,
            "actions": [action.to_dict() for action in self.actions],
            "replay_reference": copy.deepcopy(self.replay_reference),
            "rollback_reference": copy.deepcopy(self.rollback_reference),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class RuntimeRecoveryPlanReport:
    ok: bool
    plan: RuntimeRecoveryPlan
    status: str
    rollback_required: bool
    replay_required: bool
    verification_required: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["plan"] = self.plan.to_dict()
        return payload


class RuntimeRecoveryPlanEvaluator:
    def evaluate(
        self,
        *,
        recovery_id: str,
        source_failure: Any,
        source_session_id: str = "",
        task_id: str = "",
        replay_reference: dict[str, Any] | None = None,
        rollback_reference: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeRecoveryPlanReport:
        plan = build_runtime_recovery_plan(
            recovery_id=recovery_id,
            source_failure=source_failure,
            source_session_id=source_session_id,
            task_id=task_id,
            replay_reference=replay_reference,
            rollback_reference=rollback_reference,
            metadata=metadata,
        )

        return RuntimeRecoveryPlanReport(
            ok=plan.status != RECOVERY_STATUS_UNRECOVERABLE,
            plan=plan,
            status=plan.status,
            rollback_required=plan.rollback_required,
            replay_required=plan.replay_required,
            verification_required=plan.verification_required,
            errors=[] if plan.status != RECOVERY_STATUS_UNRECOVERABLE else ["runtime_recovery_unrecoverable"],
            warnings=[],
            metadata=copy.deepcopy(plan.metadata),
        )


def normalize_runtime_failure(
    source_failure: Any,
    *,
    source_session_id: str = "",
    task_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> RuntimeRecoveryFailure:
    if isinstance(source_failure, RuntimeRecoveryFailure):
        merged_metadata = source_failure.metadata
        if metadata:
            merged_metadata = {**merged_metadata, **dict(metadata)}
        return RuntimeRecoveryFailure(
            failure_type=source_failure.failure_type,
            message=source_failure.message,
            source=source_failure.source,
            status=source_failure.status,
            source_session_id=source_failure.source_session_id or source_session_id,
            task_id=source_failure.task_id or task_id,
            step_id=source_failure.step_id,
            payload=source_failure.payload,
            metadata=merged_metadata,
            observed_at=source_failure.observed_at,
        )

    payload = _copy_dict(source_failure)
    failure_type = _string(
        payload.get("failure_type")
        or payload.get("type")
        or payload.get("reason")
        or payload.get("error_type"),
        "runtime_failure",
    )
    message = _string(
        payload.get("failure_message")
        or payload.get("message")
        or payload.get("error")
        or payload.get("reason"),
        failure_type,
    )
    resolved_source_session_id = _string(
        payload.get("source_session_id") or payload.get("session_id"),
        source_session_id,
    )
    resolved_task_id = _string(payload.get("task_id"), task_id)

    return RuntimeRecoveryFailure(
        failure_type=failure_type,
        message=message,
        source=_string(payload.get("source"), "runtime"),
        status=_string(payload.get("status"), "failed"),
        source_session_id=resolved_source_session_id,
        task_id=resolved_task_id,
        step_id=_string(payload.get("step_id") or payload.get("step_index")),
        payload=payload,
        metadata={**_copy_dict(payload.get("metadata")), **dict(metadata or {})},
    )


def build_runtime_recovery_plan(
    *,
    recovery_id: str,
    source_failure: Any,
    source_session_id: str = "",
    task_id: str = "",
    replay_reference: dict[str, Any] | None = None,
    rollback_reference: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> RuntimeRecoveryPlan:
    failure = normalize_runtime_failure(
        source_failure,
        source_session_id=source_session_id,
        task_id=task_id,
        metadata=metadata,
    )

    failure_type = failure.failure_type.strip().lower()

    rollback_required = bool(
        failure_type in ROLLBACK_REQUIRING_FAILURE_TYPES
        or failure.payload.get("rollback_required") is True
        or failure.metadata.get("rollback_required") is True
    )

    unrecoverable = bool(
        failure_type in UNRECOVERABLE_FAILURE_TYPES
        or failure.payload.get("unrecoverable") is True
        or failure.metadata.get("unrecoverable") is True
    )

    replay_required = not unrecoverable
    verification_required = not unrecoverable

    status = RECOVERY_STATUS_PLANNED

    if rollback_required:
        status = RECOVERY_STATUS_ROLLBACK_REQUIRED

    if unrecoverable:
        status = RECOVERY_STATUS_UNRECOVERABLE

    seed = {
        "recovery_id": recovery_id,
        "source_session_id": failure.source_session_id,
        "failure": failure.to_dict(),
    }

    plan_id = "runtime-recovery-plan-" + stable_recovery_fingerprint(seed)[:16]

    actions: list[RuntimeRecoveryAction] = [
        RuntimeRecoveryAction(
            action_id=f"{plan_id}-detect",
            action_type="detect_failure",
            reason="capture source runtime failure",
            payload={"failure_type": failure.failure_type, "source": failure.source},
            status="completed",
        ),
        RuntimeRecoveryAction(
            action_id=f"{plan_id}-plan",
            action_type="build_recovery_plan",
            reason="derive recovery route from failure metadata",
            payload={"rollback_required": rollback_required, "unrecoverable": unrecoverable},
            status="completed",
        ),
    ]

    if replay_required:
        actions.append(
            RuntimeRecoveryAction(
                action_id=f"{plan_id}-replay",
                action_type="attach_replay_evidence",
                reason="replay evidence is required before recovery verification",
                payload=copy.deepcopy(replay_reference or {}),
            )
        )

    if rollback_required:
        actions.append(
            RuntimeRecoveryAction(
                action_id=f"{plan_id}-rollback",
                action_type="prepare_rollback",
                reason="failure can leave partial runtime mutation state",
                payload=copy.deepcopy(rollback_reference or {"mode": "manual_or_governed_rollback"}),
            )
        )

    if verification_required:
        actions.append(
            RuntimeRecoveryAction(
                action_id=f"{plan_id}-verify",
                action_type="verify_recovery",
                reason="recovery chain must be verified before continuation",
            )
        )

    if unrecoverable:
        actions.append(
            RuntimeRecoveryAction(
                action_id=f"{plan_id}-stop",
                action_type="mark_unrecoverable",
                reason="policy or approval state prevents automatic recovery",
                status="completed",
            )
        )

    return RuntimeRecoveryPlan(
        plan_id=plan_id,
        recovery_id=str(recovery_id or plan_id),
        source_session_id=failure.source_session_id or str(source_session_id or ""),
        source_failure=failure,
        status=status,
        rollback_required=rollback_required,
        replay_required=replay_required,
        verification_required=verification_required,
        actions=actions,
        replay_reference=copy.deepcopy(replay_reference or {}),
        rollback_reference=copy.deepcopy(rollback_reference or {}),
        metadata=copy.deepcopy(metadata or {}),
    )


def evaluate_runtime_recovery_plan(
    *,
    recovery_id: str,
    source_failure: Any,
    source_session_id: str = "",
    task_id: str = "",
    replay_reference: dict[str, Any] | None = None,
    rollback_reference: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> RuntimeRecoveryPlanReport:
    return RuntimeRecoveryPlanEvaluator().evaluate(
        recovery_id=recovery_id,
        source_failure=source_failure,
        source_session_id=source_session_id,
        task_id=task_id,
        replay_reference=replay_reference,
        rollback_reference=rollback_reference,
        metadata=metadata,
    )


def runtime_recovery_plan_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}

    to_dict = getattr(value, "to_dict", None)

    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, dict):
            return payload

    if isinstance(value, dict):
        return copy.deepcopy(value)

    return {
        "plan_id": _string(getattr(value, "plan_id", "")),
        "status": _string(getattr(value, "status", "")),
    }


__all__ = [
    "RECOVERY_STATUS_PLANNED",
    "RECOVERY_STATUS_ROLLBACK_REQUIRED",
    "RECOVERY_STATUS_UNRECOVERABLE",
    "RuntimeRecoveryAction",
    "RuntimeRecoveryFailure",
    "RuntimeRecoveryPlan",
    "RuntimeRecoveryPlanReport",
    "RuntimeRecoveryPlanEvaluator",
    "build_runtime_recovery_plan",
    "evaluate_runtime_recovery_plan",
    "runtime_recovery_plan_to_dict",
    "normalize_runtime_failure",
    "stable_recovery_fingerprint",
    "utc_timestamp",
]
