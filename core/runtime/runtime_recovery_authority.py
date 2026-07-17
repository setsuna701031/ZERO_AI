from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


AUTHORITY_APPLY_STATUS_APPLIED = "applied"
AUTHORITY_APPLY_STATUS_BLOCKED = "blocked"
AUTHORITY_APPLY_STATUS_REVIEW_REQUIRED = "review_required"
AUTHORITY_APPLY_STATUS_FAILED = "failed"


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


def _text(*values: Any, default: str = "") -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return default


@dataclass(frozen=True)
class RuntimeRecoveryAuthorityApplyResult:
    apply_id: str
    recovery_id: str
    source_session_id: str
    status: str
    applied: bool
    authority_owner: str
    transition_action: str
    requested_patch: dict[str, Any] = field(default_factory=dict)
    applied_state: dict[str, Any] = field(default_factory=dict)
    pipeline: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_timestamp)
    fingerprint: str = ""

    def __post_init__(self) -> None:
        events = [copy.deepcopy(item) for item in self.audit_events if isinstance(item, dict)]
        object.__setattr__(self, "audit_events", events)
        if not self.fingerprint:
            object.__setattr__(
                self,
                "fingerprint",
                _stable_fingerprint(self.to_dict(include_fingerprint=False)),
            )

    def to_dict(self, include_fingerprint: bool = True) -> dict[str, Any]:
        payload = {
            "artifact_type": "runtime_recovery_authority_apply_result",
            "apply_id": self.apply_id,
            "recovery_id": self.recovery_id,
            "source_session_id": self.source_session_id,
            "status": self.status,
            "applied": self.applied,
            "authority_owner": self.authority_owner,
            "transition_action": self.transition_action,
            "requested_patch": copy.deepcopy(self.requested_patch),
            "applied_state": copy.deepcopy(self.applied_state),
            "pipeline": copy.deepcopy(self.pipeline),
            "reason": self.reason,
            "audit_events": copy.deepcopy(self.audit_events),
            "created_at": self.created_at,
        }
        if include_fingerprint:
            payload["fingerprint"] = self.fingerprint
            payload["verified"] = self.verify()
        return payload

    def verify(self) -> bool:
        return self.fingerprint == _stable_fingerprint(self.to_dict(include_fingerprint=False))


def build_recovery_authority_apply_id(recovery_id: str, source_session_id: str = "") -> str:
    seed = {
        "kind": "runtime_recovery_authority_apply",
        "recovery_id": str(recovery_id or ""),
        "source_session_id": str(source_session_id or ""),
    }
    return "runtime-recovery-authority-apply-" + _stable_fingerprint(seed)[:16]


def _resolve_authority_status(pipeline_payload: dict[str, Any]) -> tuple[str, bool, str]:
    final_status = str(pipeline_payload.get("final_status") or "").strip().lower()
    patch = pipeline_payload.get("runtime_state_patch") if isinstance(pipeline_payload.get("runtime_state_patch"), dict) else {}

    if not patch:
        return AUTHORITY_APPLY_STATUS_FAILED, False, "runtime_state_patch_missing"

    if final_status == "ready_to_continue":
        return AUTHORITY_APPLY_STATUS_APPLIED, True, "pipeline_ready_to_continue"

    if final_status == "blocked":
        return AUTHORITY_APPLY_STATUS_BLOCKED, False, "pipeline_blocked"

    if final_status == "review_required":
        return AUTHORITY_APPLY_STATUS_REVIEW_REQUIRED, False, "pipeline_review_required"

    return AUTHORITY_APPLY_STATUS_FAILED, False, "pipeline_status_not_applicable"


def apply_recovery_pipeline_transition(
    *,
    task_runtime: Any,
    task: dict[str, Any],
    current_state: dict[str, Any],
    pipeline_result: Any,
    allow_terminal_write: bool = False,
    save: bool = False,
) -> RuntimeRecoveryAuthorityApplyResult:
    pipeline_payload = _as_dict(pipeline_result)
    recovery_id = _text(pipeline_payload.get("recovery_id"), default="runtime-recovery")
    source_session_id = _text(pipeline_payload.get("source_session_id"))
    patch = copy.deepcopy(
        pipeline_payload.get("runtime_state_patch")
        if isinstance(pipeline_payload.get("runtime_state_patch"), dict)
        else {}
    )

    status, should_apply, reason = _resolve_authority_status(pipeline_payload)

    owner = "runtime_recovery_authority"
    action = "apply_recovery_runtime_state_patch"
    applied_state: dict[str, Any] = {}

    if should_apply:
        apply_method = getattr(task_runtime, "apply_runtime_transition", None)
        if not callable(apply_method):
            status = AUTHORITY_APPLY_STATUS_FAILED
            should_apply = False
            reason = "task_runtime_apply_runtime_transition_missing"
        else:
            try:
                applied_state = apply_method(
                    task,
                    current_state,
                    owner=owner,
                    action=action,
                    updates=patch,
                    save=save,
                    allow_terminal_write=allow_terminal_write,
                )
                if not isinstance(applied_state, dict):
                    applied_state = {}
                    status = AUTHORITY_APPLY_STATUS_FAILED
                    should_apply = False
                    reason = "task_runtime_returned_invalid_state"
            except Exception as exc:
                applied_state = {}
                status = AUTHORITY_APPLY_STATUS_FAILED
                should_apply = False
                reason = str(exc) or exc.__class__.__name__

    audit_events = [
        {
            "event_type": "runtime_recovery_authority_evaluated",
            "recovery_id": recovery_id,
            "source_session_id": source_session_id,
            "authority_status": status,
            "will_apply": should_apply,
            "reason": reason,
        }
    ]
    if should_apply:
        audit_events.append(
            {
                "event_type": "runtime_recovery_authority_applied",
                "recovery_id": recovery_id,
                "source_session_id": source_session_id,
                "transition_owner": owner,
                "transition_action": action,
            }
        )
    else:
        audit_events.append(
            {
                "event_type": "runtime_recovery_authority_not_applied",
                "recovery_id": recovery_id,
                "source_session_id": source_session_id,
                "reason": reason,
            }
        )

    return RuntimeRecoveryAuthorityApplyResult(
        apply_id=build_recovery_authority_apply_id(recovery_id, source_session_id),
        recovery_id=recovery_id,
        source_session_id=source_session_id,
        status=status,
        applied=should_apply,
        authority_owner=owner,
        transition_action=action,
        requested_patch=patch,
        applied_state=applied_state,
        pipeline=pipeline_payload,
        reason=reason,
        audit_events=audit_events,
    )


def run_recovery_pipeline_and_apply_transition(
    *,
    task_runtime: Any,
    task: dict[str, Any],
    current_state: dict[str, Any],
    source_failure: dict[str, Any] | None = None,
    approval_granted: bool = False,
    metadata: dict[str, Any] | None = None,
    pipeline: Any | None = None,
    allow_terminal_write: bool = False,
    save: bool = False,
) -> RuntimeRecoveryAuthorityApplyResult:
    if pipeline is None:
        from core.runtime.runtime_recovery_pipeline import RuntimeRecoveryPipeline

        pipeline = RuntimeRecoveryPipeline()

    run_method = getattr(pipeline, "run_failure_recovery", None)
    if callable(run_method):
        pipeline_result = run_method(
            source_state=current_state,
            source_failure=source_failure or {},
            approval_granted=approval_granted,
            metadata=metadata or {},
        )
    else:
        raise TypeError("pipeline_missing_run_failure_recovery")

    return apply_recovery_pipeline_transition(
        task_runtime=task_runtime,
        task=task,
        current_state=current_state,
        pipeline_result=pipeline_result,
        allow_terminal_write=allow_terminal_write,
        save=save,
    )


__all__ = [
    "AUTHORITY_APPLY_STATUS_APPLIED",
    "AUTHORITY_APPLY_STATUS_BLOCKED",
    "AUTHORITY_APPLY_STATUS_REVIEW_REQUIRED",
    "AUTHORITY_APPLY_STATUS_FAILED",
    "RuntimeRecoveryAuthorityApplyResult",
    "apply_recovery_pipeline_transition",
    "build_recovery_authority_apply_id",
    "run_recovery_pipeline_and_apply_transition",
]
