from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from core.runtime.runtime_recovery_state import (
    RECOVERY_CONTINUATION_BLOCKED,
    RECOVERY_CONTINUATION_READY,
    RECOVERY_CONTINUATION_REQUIRES_REVIEW,
    RECOVERY_CONTINUATION_REQUIRES_ROLLBACK,
    RECOVERY_CONTINUATION_UNRECOVERABLE,
    RECOVERY_EXECUTION_STATUS_BLOCKED,
    RECOVERY_EXECUTION_STATUS_COMPLETED,
    RECOVERY_EXECUTION_STATUS_FAILED,
    normalize_recovery_chain_payload,
)


CONTINUATION_STATUS_PLANNED = "planned"
CONTINUATION_STATUS_READY = "ready"
CONTINUATION_STATUS_BLOCKED = "blocked"
CONTINUATION_STATUS_APPLIED = "applied"
CONTINUATION_STATUS_REQUIRES_REVIEW = "requires_review"
CONTINUATION_STATUS_FAILED = "failed"

CONTINUATION_ACTION_PREPARE = "prepare_runtime_continuation"
CONTINUATION_ACTION_RESUME = "resume_runtime"
CONTINUATION_ACTION_BLOCK = "block_runtime_continuation"
CONTINUATION_ACTION_REQUIRE_ROLLBACK = "require_rollback_before_continuation"
CONTINUATION_ACTION_REQUIRE_REVIEW = "require_review_before_continuation"


ContinuationHandler = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _copy_dict(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _copy_list(value: Any) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


def normalize_recovery_execution_payload(result: Any) -> dict[str, Any]:
    if hasattr(result, "to_dict") and callable(result.to_dict):
        payload = result.to_dict()
        return copy.deepcopy(payload if isinstance(payload, dict) else {})
    return _copy_dict(result)


def build_continuation_id(recovery_id: str, execution_id: str, payload: dict[str, Any] | None = None) -> str:
    seed = {
        "recovery_id": str(recovery_id or ""),
        "execution_id": str(execution_id or ""),
        "payload": _copy_dict(payload),
        "created_at": utc_timestamp(),
    }
    return "runtime-recovery-continuation-" + _stable_fingerprint(seed)[:16]


@dataclass(frozen=True)
class RuntimeContinuationAction:
    action_id: str
    action_type: str
    status: str = CONTINUATION_STATUS_PLANNED
    reason: str = ""
    required: bool = True
    payload: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "status": self.status,
            "reason": self.reason,
            "required": self.required,
            "payload": copy.deepcopy(self.payload),
            "result": copy.deepcopy(self.result),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class RuntimeContinuationPlan:
    continuation_id: str
    recovery_id: str
    execution_id: str
    source_session_id: str
    status: str
    decision: str
    reason: str
    actions: list[dict[str, Any]] = field(default_factory=list)
    source_state_snapshot: dict[str, Any] = field(default_factory=dict)
    target_runtime_status: str = "running"
    requires_approval: bool = False
    requires_review: bool = False
    requires_rollback: bool = False
    safe_to_apply: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "continuation_id": self.continuation_id,
            "recovery_id": self.recovery_id,
            "execution_id": self.execution_id,
            "source_session_id": self.source_session_id,
            "status": self.status,
            "decision": self.decision,
            "reason": self.reason,
            "actions": [copy.deepcopy(item) for item in self.actions],
            "source_state_snapshot": copy.deepcopy(self.source_state_snapshot),
            "target_runtime_status": self.target_runtime_status,
            "requires_approval": self.requires_approval,
            "requires_review": self.requires_review,
            "requires_rollback": self.requires_rollback,
            "safe_to_apply": self.safe_to_apply,
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class RuntimeContinuationResult:
    continuation_id: str
    recovery_id: str
    execution_id: str
    source_session_id: str
    status: str
    decision: str
    applied: bool = False
    source_state_before: dict[str, Any] = field(default_factory=dict)
    source_state_after: dict[str, Any] = field(default_factory=dict)
    source_state_mutated: bool = False
    action_results: list[dict[str, Any]] = field(default_factory=list)
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "continuation_id": self.continuation_id,
            "recovery_id": self.recovery_id,
            "execution_id": self.execution_id,
            "source_session_id": self.source_session_id,
            "status": self.status,
            "decision": self.decision,
            "applied": self.applied,
            "source_state_before": copy.deepcopy(self.source_state_before),
            "source_state_after": copy.deepcopy(self.source_state_after),
            "source_state_mutated": self.source_state_mutated,
            "action_results": [copy.deepcopy(item) for item in self.action_results],
            "audit_events": [copy.deepcopy(item) for item in self.audit_events],
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class RuntimeRecoveryContinuationPolicy:
    def __init__(self, *, allow_auto_apply: bool = False) -> None:
        self.allow_auto_apply = bool(allow_auto_apply)

    def build_plan(
        self,
        *,
        execution_payload: dict[str, Any],
        source_state: dict[str, Any],
        recovery_chain: dict[str, Any] | None = None,
        approval: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeContinuationPlan:
        recovery_id = str(execution_payload.get("recovery_id") or "").strip()
        execution_id = str(execution_payload.get("execution_id") or "").strip()
        source_session_id = str(execution_payload.get("source_session_id") or "").strip()
        continuation_id = build_continuation_id(recovery_id, execution_id, {"metadata": metadata or {}})
        execution_status = str(execution_payload.get("status") or "").strip().lower()
        continuation_decision = str(execution_payload.get("continuation_decision") or "").strip().lower()
        chain_payload = normalize_recovery_chain_payload(recovery_chain) if recovery_chain is not None else {}
        chain_status = str(chain_payload.get("status") or execution_payload.get("recovery_chain_status") or "").strip().lower()
        verification = execution_payload.get("verification_snapshot") if isinstance(execution_payload.get("verification_snapshot"), dict) else {}
        verified = bool(verification.get("verified"))
        approved = self._is_approved(approval)

        actions: list[RuntimeContinuationAction] = []
        target_status = "running"
        requires_review = False
        requires_approval = False
        requires_rollback = False
        safe_to_apply = False
        status = CONTINUATION_STATUS_REQUIRES_REVIEW
        decision = RECOVERY_CONTINUATION_REQUIRES_REVIEW
        reason = "runtime continuation requires review"

        if execution_status in {RECOVERY_EXECUTION_STATUS_BLOCKED, RECOVERY_EXECUTION_STATUS_FAILED}:
            status = CONTINUATION_STATUS_BLOCKED
            decision = RECOVERY_CONTINUATION_BLOCKED
            requires_review = True
            requires_approval = True
            reason = "recovery execution did not complete"
            actions.append(self._action(continuation_id, CONTINUATION_ACTION_BLOCK, reason, required=True))
        elif continuation_decision == RECOVERY_CONTINUATION_UNRECOVERABLE or chain_status == "unrecoverable":
            status = CONTINUATION_STATUS_BLOCKED
            decision = RECOVERY_CONTINUATION_UNRECOVERABLE
            requires_review = True
            requires_approval = True
            reason = "recovery chain is unrecoverable"
            actions.append(self._action(continuation_id, CONTINUATION_ACTION_BLOCK, reason, required=True))
        elif continuation_decision == RECOVERY_CONTINUATION_REQUIRES_ROLLBACK or chain_status == "rollback_required":
            status = CONTINUATION_STATUS_BLOCKED
            decision = RECOVERY_CONTINUATION_REQUIRES_ROLLBACK
            requires_review = True
            requires_approval = True
            requires_rollback = True
            reason = "rollback is required before runtime continuation"
            actions.append(self._action(continuation_id, CONTINUATION_ACTION_REQUIRE_ROLLBACK, reason, required=True))
        elif continuation_decision == RECOVERY_CONTINUATION_READY and execution_status == RECOVERY_EXECUTION_STATUS_COMPLETED and verified:
            status = CONTINUATION_STATUS_READY
            decision = RECOVERY_CONTINUATION_READY
            requires_review = False
            requires_approval = not approved
            safe_to_apply = approved or self.allow_auto_apply
            reason = "recovery execution is verified and ready for controlled continuation"
            actions.append(
                self._action(
                    continuation_id,
                    CONTINUATION_ACTION_PREPARE,
                    "prepare controlled runtime continuation",
                    payload={"target_runtime_status": target_status, "verified": verified},
                    required=True,
                )
            )
            actions.append(
                self._action(
                    continuation_id,
                    CONTINUATION_ACTION_RESUME,
                    "resume runtime only through approved continuation surface",
                    payload={"target_runtime_status": target_status},
                    required=False,
                )
            )
        else:
            status = CONTINUATION_STATUS_REQUIRES_REVIEW
            decision = RECOVERY_CONTINUATION_REQUIRES_REVIEW
            requires_review = True
            requires_approval = True
            reason = "recovery continuation is not verified as ready"
            actions.append(self._action(continuation_id, CONTINUATION_ACTION_REQUIRE_REVIEW, reason, required=True))

        return RuntimeContinuationPlan(
            continuation_id=continuation_id,
            recovery_id=recovery_id,
            execution_id=execution_id,
            source_session_id=source_session_id,
            status=status,
            decision=decision,
            reason=reason,
            actions=[item.to_dict() for item in actions],
            source_state_snapshot=copy.deepcopy(source_state),
            target_runtime_status=target_status,
            requires_approval=requires_approval,
            requires_review=requires_review,
            requires_rollback=requires_rollback,
            safe_to_apply=safe_to_apply,
            metadata=copy.deepcopy(metadata or {}),
        )

    def _action(
        self,
        continuation_id: str,
        action_type: str,
        reason: str,
        *,
        payload: dict[str, Any] | None = None,
        required: bool = True,
    ) -> RuntimeContinuationAction:
        return RuntimeContinuationAction(
            action_id=f"{continuation_id}-{action_type}",
            action_type=action_type,
            reason=reason,
            required=required,
            payload=copy.deepcopy(payload or {}),
        )

    def _is_approved(self, approval: dict[str, Any] | None) -> bool:
        if not isinstance(approval, dict):
            return False
        return bool(approval.get("approved") is True or str(approval.get("status") or "").lower() == "approved")


class RuntimeRecoveryContinuationLayer:
    def __init__(
        self,
        *,
        policy: RuntimeRecoveryContinuationPolicy | None = None,
        journal: Any = None,
        handler: ContinuationHandler | None = None,
    ) -> None:
        self.policy = policy if policy is not None else RuntimeRecoveryContinuationPolicy()
        self.journal = journal
        self.handler = handler
        self._plans: dict[str, RuntimeContinuationPlan] = {}
        self._results: dict[str, RuntimeContinuationResult] = {}

    def plan_continuation(
        self,
        execution_result: Any,
        *,
        source_state: dict[str, Any] | None = None,
        recovery_chain: Any = None,
        approval: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeContinuationPlan:
        execution_payload = normalize_recovery_execution_payload(execution_result)
        chain_payload = normalize_recovery_chain_payload(recovery_chain) if recovery_chain is not None else {}
        plan = self.policy.build_plan(
            execution_payload=execution_payload,
            source_state=_copy_dict(source_state),
            recovery_chain=chain_payload,
            approval=approval,
            metadata=metadata,
        )
        self._plans[plan.continuation_id] = copy.deepcopy(plan)
        self._append_journal("runtime_recovery_continuation_plan", plan.to_dict(), {"recovery_id": plan.recovery_id})
        return plan

    def apply_continuation(
        self,
        continuation_plan: Any,
        *,
        source_state: dict[str, Any] | None = None,
        approval: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeContinuationResult:
        plan = self._normalize_plan(continuation_plan)
        before = _copy_dict(source_state) or _copy_dict(plan.get("source_state_snapshot"))
        after = copy.deepcopy(before)
        audit_events: list[dict[str, Any]] = []
        action_results: list[dict[str, Any]] = []
        approved = self._is_approved(approval)
        safe_to_apply = bool(plan.get("safe_to_apply"))

        self._append_audit(
            audit_events,
            plan=plan,
            event_type="runtime_continuation_apply_started",
            payload={"plan_status": plan.get("status"), "safe_to_apply": safe_to_apply, "approved": approved},
        )

        if str(plan.get("decision") or "") != RECOVERY_CONTINUATION_READY:
            status = CONTINUATION_STATUS_BLOCKED
            applied = False
            self._append_audit(
                audit_events,
                plan=plan,
                event_type="runtime_continuation_blocked",
                payload={"reason": plan.get("reason") or "continuation_not_ready"},
            )
            result = RuntimeContinuationResult(
                continuation_id=str(plan.get("continuation_id") or ""),
                recovery_id=str(plan.get("recovery_id") or ""),
                execution_id=str(plan.get("execution_id") or ""),
                source_session_id=str(plan.get("source_session_id") or ""),
                status=status,
                decision=str(plan.get("decision") or RECOVERY_CONTINUATION_BLOCKED),
                applied=applied,
                source_state_before=before,
                source_state_after=after,
                source_state_mutated=False,
                action_results=action_results,
                audit_events=audit_events,
                metadata=copy.deepcopy(metadata or {}),
            )
            self._store_result(result)
            return result

        if not safe_to_apply and not approved:
            status = CONTINUATION_STATUS_REQUIRES_REVIEW
            applied = False
            self._append_audit(
                audit_events,
                plan=plan,
                event_type="runtime_continuation_review_required",
                payload={"reason": "explicit approval required before applying continuation"},
            )
            result = RuntimeContinuationResult(
                continuation_id=str(plan.get("continuation_id") or ""),
                recovery_id=str(plan.get("recovery_id") or ""),
                execution_id=str(plan.get("execution_id") or ""),
                source_session_id=str(plan.get("source_session_id") or ""),
                status=status,
                decision=RECOVERY_CONTINUATION_REQUIRES_REVIEW,
                applied=applied,
                source_state_before=before,
                source_state_after=after,
                source_state_mutated=False,
                action_results=action_results,
                audit_events=audit_events,
                metadata=copy.deepcopy(metadata or {}),
            )
            self._store_result(result)
            return result

        try:
            if self.handler is not None:
                handler_result = self.handler(copy.deepcopy(plan), {"source_state": copy.deepcopy(after), "approval": copy.deepcopy(approval or {})})
                if isinstance(handler_result, dict) and isinstance(handler_result.get("source_state"), dict):
                    after = copy.deepcopy(handler_result["source_state"])
                action_results.append(copy.deepcopy(handler_result if isinstance(handler_result, dict) else {"ok": True}))
            else:
                after["status"] = str(plan.get("target_runtime_status") or "running")
                after["runtime_recovery_continuation"] = {
                    "continuation_id": str(plan.get("continuation_id") or ""),
                    "recovery_id": str(plan.get("recovery_id") or ""),
                    "execution_id": str(plan.get("execution_id") or ""),
                    "continued_at": utc_timestamp(),
                    "source": "runtime_recovery_continuation_layer",
                }
                action_results.append({"ok": True, "mode": "default_state_continuation", "target_runtime_status": after.get("status")})
            status = CONTINUATION_STATUS_APPLIED
            applied = True
            self._append_audit(
                audit_events,
                plan=plan,
                event_type="runtime_continuation_applied",
                payload={"target_runtime_status": after.get("status")},
            )
        except Exception as exc:
            status = CONTINUATION_STATUS_FAILED
            applied = False
            action_results.append({"ok": False, "error": str(exc)})
            self._append_audit(
                audit_events,
                plan=plan,
                event_type="runtime_continuation_failed",
                payload={"error": str(exc)},
            )

        result = RuntimeContinuationResult(
            continuation_id=str(plan.get("continuation_id") or ""),
            recovery_id=str(plan.get("recovery_id") or ""),
            execution_id=str(plan.get("execution_id") or ""),
            source_session_id=str(plan.get("source_session_id") or ""),
            status=status,
            decision=RECOVERY_CONTINUATION_READY if applied else RECOVERY_CONTINUATION_REQUIRES_REVIEW,
            applied=applied,
            source_state_before=before,
            source_state_after=after,
            source_state_mutated=before != after,
            action_results=action_results,
            audit_events=audit_events,
            metadata=copy.deepcopy(metadata or {}),
        )
        self._store_result(result)
        return result

    def get_plan(self, continuation_id: str) -> RuntimeContinuationPlan | None:
        item = self._plans.get(str(continuation_id or ""))
        return copy.deepcopy(item) if item is not None else None

    def get_result(self, continuation_id: str) -> RuntimeContinuationResult | None:
        item = self._results.get(str(continuation_id or ""))
        return copy.deepcopy(item) if item is not None else None

    def _normalize_plan(self, plan: Any) -> dict[str, Any]:
        if hasattr(plan, "to_dict") and callable(plan.to_dict):
            payload = plan.to_dict()
            return copy.deepcopy(payload if isinstance(payload, dict) else {})
        return _copy_dict(plan)

    def _store_result(self, result: RuntimeContinuationResult) -> None:
        self._results[result.continuation_id] = copy.deepcopy(result)
        self._append_journal("runtime_recovery_continuation_result", result.to_dict(), {"recovery_id": result.recovery_id})

    def _append_audit(self, audit_events: list[dict[str, Any]], *, plan: dict[str, Any], event_type: str, payload: dict[str, Any]) -> None:
        event = {
            "event_type": event_type,
            "continuation_id": str(plan.get("continuation_id") or ""),
            "recovery_id": str(plan.get("recovery_id") or ""),
            "execution_id": str(plan.get("execution_id") or ""),
            "payload": copy.deepcopy(payload),
            "timestamp": utc_timestamp(),
            "source": "runtime_recovery_continuation_layer",
        }
        audit_events.append(event)
        self._append_journal("runtime_recovery_continuation_audit_event", event, {"recovery_id": event["recovery_id"]})

    def _append_journal(self, record_type: str, payload: dict[str, Any], metadata: dict[str, Any]) -> None:
        if self.journal is None:
            return
        try:
            self.journal.append(record_type, payload=payload, metadata=metadata)
        except Exception:
            return

    def _is_approved(self, approval: dict[str, Any] | None) -> bool:
        if not isinstance(approval, dict):
            return False
        return bool(approval.get("approved") is True or str(approval.get("status") or "").lower() == "approved")


__all__ = [
    "CONTINUATION_ACTION_BLOCK",
    "CONTINUATION_ACTION_PREPARE",
    "CONTINUATION_ACTION_REQUIRE_REVIEW",
    "CONTINUATION_ACTION_REQUIRE_ROLLBACK",
    "CONTINUATION_ACTION_RESUME",
    "CONTINUATION_STATUS_APPLIED",
    "CONTINUATION_STATUS_BLOCKED",
    "CONTINUATION_STATUS_FAILED",
    "CONTINUATION_STATUS_PLANNED",
    "CONTINUATION_STATUS_READY",
    "CONTINUATION_STATUS_REQUIRES_REVIEW",
    "RuntimeContinuationAction",
    "RuntimeContinuationPlan",
    "RuntimeContinuationResult",
    "RuntimeRecoveryContinuationLayer",
    "RuntimeRecoveryContinuationPolicy",
    "build_continuation_id",
    "normalize_recovery_execution_payload",
]
