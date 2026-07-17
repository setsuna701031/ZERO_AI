from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

try:
    from core.runtime.runtime_recovery_governance import (
        STATUS_ALLOWED,
        STATUS_BLOCKED,
        STATUS_REVIEW_REQUIRED,
        evaluate_recovery_governance,
    )
except Exception:  # pragma: no cover - compatibility fallback
    STATUS_ALLOWED = "allowed"
    STATUS_BLOCKED = "blocked"
    STATUS_REVIEW_REQUIRED = "review_required"

    @dataclass(frozen=True)
    class _FallbackGovernanceResult:
        status: str
        risk: str
        approval_required: bool

    def evaluate_recovery_governance(payload: dict[str, Any]) -> _FallbackGovernanceResult:
        if bool(payload.get("rollback_required")):
            return _FallbackGovernanceResult(STATUS_BLOCKED, "high", True)
        if str(payload.get("mutation_scope") or "") == "extended":
            return _FallbackGovernanceResult(STATUS_REVIEW_REQUIRED, "medium", True)
        return _FallbackGovernanceResult(STATUS_ALLOWED, "low", False)


INTEGRATION_STATUS_READY_TO_CONTINUE = "ready_to_continue"
INTEGRATION_STATUS_REVIEW_REQUIRED = "review_required"
INTEGRATION_STATUS_BLOCKED = "blocked"
INTEGRATION_STATUS_FAILED = "failed"
INTEGRATION_STATUS_SEALED = "sealed"

_ALLOWED_FINAL_STATUSES = {
    INTEGRATION_STATUS_READY_TO_CONTINUE,
    INTEGRATION_STATUS_REVIEW_REQUIRED,
    INTEGRATION_STATUS_BLOCKED,
    INTEGRATION_STATUS_FAILED,
    INTEGRATION_STATUS_SEALED,
}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return copy.deepcopy(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        converted = to_dict()
        if isinstance(converted, dict):
            return copy.deepcopy(converted)
    return {}


def _first_nonempty(*values: Any, default: str = "") -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return default


def _bool_from_payload(payload: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        if key in payload:
            return bool(payload.get(key))
    return False


@dataclass(frozen=True)
class RuntimeRecoveryIntegrationSeal:
    integration_id: str
    recovery_id: str
    source_session_id: str
    source_failure: dict[str, Any]
    chain_status: str
    execution_status: str
    continuation_status: str
    governance_status: str
    risk: str
    approval_required: bool
    approved: bool
    rollback_required: bool
    rollback_executed: bool
    final_status: str
    next_action: str
    chain: dict[str, Any] = field(default_factory=dict)
    execution: dict[str, Any] = field(default_factory=dict)
    continuation: dict[str, Any] = field(default_factory=dict)
    governance: dict[str, Any] = field(default_factory=dict)
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    sealed_at: str = field(default_factory=utc_timestamp)
    fingerprint: str = ""

    def __post_init__(self) -> None:
        final_status = str(self.final_status or "").strip() or INTEGRATION_STATUS_FAILED
        if final_status not in _ALLOWED_FINAL_STATUSES:
            final_status = INTEGRATION_STATUS_FAILED
        object.__setattr__(self, "final_status", final_status)

        audit_events = [copy.deepcopy(item) for item in self.audit_events if isinstance(item, dict)]
        object.__setattr__(self, "audit_events", audit_events)

        if not self.fingerprint:
            object.__setattr__(
                self,
                "fingerprint",
                _stable_fingerprint(self.to_dict(include_fingerprint=False)),
            )

    def to_dict(self, include_fingerprint: bool = True) -> dict[str, Any]:
        payload = {
            "artifact_type": "runtime_recovery_integration_seal",
            "integration_id": self.integration_id,
            "recovery_id": self.recovery_id,
            "source_session_id": self.source_session_id,
            "source_failure": copy.deepcopy(self.source_failure),
            "chain_status": self.chain_status,
            "execution_status": self.execution_status,
            "continuation_status": self.continuation_status,
            "governance_status": self.governance_status,
            "risk": self.risk,
            "approval_required": self.approval_required,
            "approved": self.approved,
            "rollback_required": self.rollback_required,
            "rollback_executed": self.rollback_executed,
            "final_status": self.final_status,
            "next_action": self.next_action,
            "chain": copy.deepcopy(self.chain),
            "execution": copy.deepcopy(self.execution),
            "continuation": copy.deepcopy(self.continuation),
            "governance": copy.deepcopy(self.governance),
            "audit_events": copy.deepcopy(self.audit_events),
            "sealed_at": self.sealed_at,
        }
        if include_fingerprint:
            payload["fingerprint"] = self.fingerprint
            payload["sealed"] = self.verify()
        return payload

    def verify(self) -> bool:
        return self.fingerprint == _stable_fingerprint(self.to_dict(include_fingerprint=False))


def build_recovery_integration_id(recovery_id: str, source_session_id: str = "") -> str:
    seed = {
        "recovery_id": str(recovery_id or ""),
        "source_session_id": str(source_session_id or ""),
        "kind": "runtime_recovery_integration_seal",
    }
    return "runtime-recovery-integration-" + _stable_fingerprint(seed)[:16]


def _resolve_final_status(
    *,
    governance_status: str,
    execution_status: str,
    continuation_status: str,
    approval_required: bool,
    approved: bool,
    rollback_required: bool,
    rollback_executed: bool,
) -> tuple[str, str]:
    if governance_status == STATUS_BLOCKED and not approved:
        return INTEGRATION_STATUS_BLOCKED, "wait_for_recovery_approval"

    if governance_status == STATUS_REVIEW_REQUIRED and not approved:
        return INTEGRATION_STATUS_REVIEW_REQUIRED, "wait_for_recovery_review"

    if rollback_required and not rollback_executed:
        return INTEGRATION_STATUS_REVIEW_REQUIRED, "prepare_rollback_review"

    if str(execution_status or "").strip().lower() in {"failed", "error"}:
        return INTEGRATION_STATUS_FAILED, "inspect_recovery_execution_failure"

    if str(continuation_status or "").strip().lower() in {
        "ready_to_continue",
        "continued",
        "continuable",
        "completed",
        "ok",
        "allowed",
    }:
        return INTEGRATION_STATUS_READY_TO_CONTINUE, "resume_runtime"

    if approval_required and approved:
        return INTEGRATION_STATUS_READY_TO_CONTINUE, "resume_runtime_after_approval"

    return INTEGRATION_STATUS_REVIEW_REQUIRED, "review_recovery_integration"


def seal_runtime_recovery_integration(
    *,
    chain: Any,
    execution: Any | None = None,
    continuation: Any | None = None,
    approval_granted: bool = False,
    metadata: dict[str, Any] | None = None,
) -> RuntimeRecoveryIntegrationSeal:
    chain_payload = _as_dict(chain)
    execution_payload = _as_dict(execution)
    continuation_payload = _as_dict(continuation)
    meta = copy.deepcopy(metadata or {})

    recovery_id = _first_nonempty(
        chain_payload.get("recovery_id"),
        execution_payload.get("recovery_id"),
        continuation_payload.get("recovery_id"),
        meta.get("recovery_id"),
        default="runtime-recovery",
    )
    source_session_id = _first_nonempty(
        chain_payload.get("source_session_id"),
        execution_payload.get("source_session_id"),
        continuation_payload.get("source_session_id"),
        meta.get("source_session_id"),
    )

    source_failure = copy.deepcopy(
        chain_payload.get("source_failure")
        if isinstance(chain_payload.get("source_failure"), dict)
        else execution_payload.get("source_failure")
        if isinstance(execution_payload.get("source_failure"), dict)
        else meta.get("source_failure")
        if isinstance(meta.get("source_failure"), dict)
        else {}
    )

    rollback_required = (
        _bool_from_payload(chain_payload, "rollback_required")
        or _bool_from_payload(execution_payload, "rollback_required")
        or _bool_from_payload(continuation_payload, "rollback_required")
    )
    rollback_executed = (
        _bool_from_payload(chain_payload, "rollback_executed")
        or _bool_from_payload(execution_payload, "rollback_executed")
        or _bool_from_payload(continuation_payload, "rollback_executed")
    )

    governance_input = {
        **copy.deepcopy(chain_payload),
        **copy.deepcopy(execution_payload),
        **copy.deepcopy(continuation_payload),
        "rollback_required": rollback_required,
        "rollback_executed": rollback_executed,
    }
    if "mutation_scope" in meta:
        governance_input["mutation_scope"] = meta.get("mutation_scope")

    governance_result = evaluate_recovery_governance(governance_input)
    governance_status = str(getattr(governance_result, "status", STATUS_REVIEW_REQUIRED) or STATUS_REVIEW_REQUIRED)
    risk = str(getattr(governance_result, "risk", "unknown") or "unknown")
    approval_required = bool(getattr(governance_result, "approval_required", False))
    approved = bool(approval_granted)

    chain_status = _first_nonempty(chain_payload.get("status"), chain_payload.get("final_status"), default="unknown")
    execution_status = _first_nonempty(execution_payload.get("status"), execution_payload.get("final_status"), default="unknown")
    continuation_status = _first_nonempty(
        continuation_payload.get("status"),
        continuation_payload.get("continuation_status"),
        continuation_payload.get("final_status"),
        default="unknown",
    )

    final_status, next_action = _resolve_final_status(
        governance_status=governance_status,
        execution_status=execution_status,
        continuation_status=continuation_status,
        approval_required=approval_required,
        approved=approved,
        rollback_required=rollback_required,
        rollback_executed=rollback_executed,
    )

    audit_events = [
        {
            "event_type": "recovery_integration_started",
            "recovery_id": recovery_id,
            "source_session_id": source_session_id,
        },
        {
            "event_type": "recovery_governance_evaluated",
            "status": governance_status,
            "risk": risk,
            "approval_required": approval_required,
            "approved": approved,
        },
        {
            "event_type": "recovery_integration_sealed",
            "final_status": final_status,
            "next_action": next_action,
        },
    ]

    integration_id = build_recovery_integration_id(recovery_id, source_session_id)

    return RuntimeRecoveryIntegrationSeal(
        integration_id=integration_id,
        recovery_id=recovery_id,
        source_session_id=source_session_id,
        source_failure=source_failure,
        chain_status=chain_status,
        execution_status=execution_status,
        continuation_status=continuation_status,
        governance_status=governance_status,
        risk=risk,
        approval_required=approval_required,
        approved=approved,
        rollback_required=rollback_required,
        rollback_executed=rollback_executed,
        final_status=final_status,
        next_action=next_action,
        chain=chain_payload,
        execution=execution_payload,
        continuation=continuation_payload,
        governance={
            "status": governance_status,
            "risk": risk,
            "approval_required": approval_required,
            "approved": approved,
        },
        audit_events=audit_events,
    )


__all__ = [
    "INTEGRATION_STATUS_READY_TO_CONTINUE",
    "INTEGRATION_STATUS_REVIEW_REQUIRED",
    "INTEGRATION_STATUS_BLOCKED",
    "INTEGRATION_STATUS_FAILED",
    "INTEGRATION_STATUS_SEALED",
    "RuntimeRecoveryIntegrationSeal",
    "build_recovery_integration_id",
    "seal_runtime_recovery_integration",
]
