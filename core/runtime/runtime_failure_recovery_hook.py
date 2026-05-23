from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

try:
    from core.runtime.runtime_recovery_authority import (
        AUTHORITY_APPLY_STATUS_APPLIED,
        AUTHORITY_APPLY_STATUS_BLOCKED,
        AUTHORITY_APPLY_STATUS_FAILED,
        AUTHORITY_APPLY_STATUS_REVIEW_REQUIRED,
        run_recovery_pipeline_and_apply_transition,
    )
except Exception:
    AUTHORITY_APPLY_STATUS_APPLIED = "applied"
    AUTHORITY_APPLY_STATUS_BLOCKED = "blocked"
    AUTHORITY_APPLY_STATUS_REVIEW_REQUIRED = "review_required"
    AUTHORITY_APPLY_STATUS_FAILED = "failed"

    def run_recovery_pipeline_and_apply_transition(**kwargs: Any) -> Any:
        raise RuntimeError("runtime_recovery_authority_unavailable")


FAILURE_HOOK_STATUS_RECOVERY_APPLIED = "recovery_applied"
FAILURE_HOOK_STATUS_RECOVERY_BLOCKED = "recovery_blocked"
FAILURE_HOOK_STATUS_REVIEW_REQUIRED = "review_required"
FAILURE_HOOK_STATUS_RECOVERY_FAILED = "recovery_failed"
FAILURE_HOOK_STATUS_SKIPPED = "skipped"


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


def _normalize_failure_payload(
    *,
    task: dict[str, Any],
    state: dict[str, Any],
    step: dict[str, Any] | None = None,
    step_result: dict[str, Any] | None = None,
    failure_type: str = "",
    failure_message: str = "",
) -> dict[str, Any]:
    result = copy.deepcopy(step_result if isinstance(step_result, dict) else {})
    error = result.get("error")
    if not error and failure_message:
        error = failure_message

    return {
        "task_id": _text(state.get("task_id"), task.get("task_id"), task.get("id")),
        "task_name": _text(state.get("task_name"), task.get("name")),
        "source_session_id": _text(state.get("session_id"), state.get("source_session_id")),
        "failure_type": _text(failure_type, state.get("failure_type"), result.get("failure_type"), default="runtime_failure"),
        "failure_message": _text(failure_message, state.get("failure_message"), result.get("message"), result.get("error"), default=str(error or "")),
        "error": copy.deepcopy(error),
        "step": copy.deepcopy(step if isinstance(step, dict) else {}),
        "step_result": result,
        "rollback_required": bool(
            result.get("rollback_required")
            or state.get("rollback_required")
            or task.get("rollback_required")
        ),
    }


@dataclass(frozen=True)
class RuntimeFailureRecoveryHookResult:
    hook_id: str
    recovery_id: str
    source_session_id: str
    status: str
    recovered: bool
    authority_result: dict[str, Any] = field(default_factory=dict)
    failure: dict[str, Any] = field(default_factory=dict)
    runtime_state_patch: dict[str, Any] = field(default_factory=dict)
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
            "artifact_type": "runtime_failure_recovery_hook_result",
            "hook_id": self.hook_id,
            "recovery_id": self.recovery_id,
            "source_session_id": self.source_session_id,
            "status": self.status,
            "recovered": self.recovered,
            "authority_result": copy.deepcopy(self.authority_result),
            "failure": copy.deepcopy(self.failure),
            "runtime_state_patch": copy.deepcopy(self.runtime_state_patch),
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


def build_failure_recovery_hook_id(recovery_id: str, source_session_id: str = "") -> str:
    seed = {
        "kind": "runtime_failure_recovery_hook",
        "recovery_id": str(recovery_id or ""),
        "source_session_id": str(source_session_id or ""),
    }
    return "runtime-failure-recovery-hook-" + _stable_fingerprint(seed)[:16]


def _map_authority_status(authority_status: str) -> tuple[str, bool]:
    status = str(authority_status or "").strip().lower()
    if status == AUTHORITY_APPLY_STATUS_APPLIED:
        return FAILURE_HOOK_STATUS_RECOVERY_APPLIED, True
    if status == AUTHORITY_APPLY_STATUS_BLOCKED:
        return FAILURE_HOOK_STATUS_RECOVERY_BLOCKED, False
    if status == AUTHORITY_APPLY_STATUS_REVIEW_REQUIRED:
        return FAILURE_HOOK_STATUS_REVIEW_REQUIRED, False
    return FAILURE_HOOK_STATUS_RECOVERY_FAILED, False


class RuntimeFailureRecoveryHook:
    """
    Runtime failure hook entrypoint.

    This module connects real TaskRuntime/StepExecutor failure paths to the
    governed recovery pipeline, but still preserves the runtime authority rule:
    the hook never mutates runtime state directly; it delegates patch application
    to runtime_recovery_authority -> TaskRuntime.apply_runtime_transition().
    """

    def __init__(
        self,
        *,
        task_runtime: Any,
        pipeline: Any | None = None,
        auto_recover: bool = True,
    ) -> None:
        self.task_runtime = task_runtime
        self.pipeline = pipeline
        self.auto_recover = bool(auto_recover)

    def handle_failure(
        self,
        *,
        task: dict[str, Any],
        current_state: dict[str, Any],
        step: dict[str, Any] | None = None,
        step_result: dict[str, Any] | None = None,
        failure_type: str = "",
        failure_message: str = "",
        approval_granted: bool = False,
        metadata: dict[str, Any] | None = None,
        save: bool = False,
        allow_terminal_write: bool = False,
    ) -> RuntimeFailureRecoveryHookResult:
        task_payload = copy.deepcopy(task if isinstance(task, dict) else {})
        state_payload = copy.deepcopy(current_state if isinstance(current_state, dict) else {})
        meta = copy.deepcopy(metadata if isinstance(metadata, dict) else {})

        failure = _normalize_failure_payload(
            task=task_payload,
            state=state_payload,
            step=step,
            step_result=step_result,
            failure_type=failure_type,
            failure_message=failure_message,
        )

        recovery_id = _text(
            meta.get("recovery_id"),
            state_payload.get("recovery_id"),
            failure.get("recovery_id"),
            default="runtime-recovery-" + _stable_fingerprint({"state": state_payload, "failure": failure})[:12],
        )
        source_session_id = _text(
            meta.get("source_session_id"),
            state_payload.get("session_id"),
            state_payload.get("source_session_id"),
            failure.get("source_session_id"),
        )

        if not self.auto_recover:
            return self._build_result(
                recovery_id=recovery_id,
                source_session_id=source_session_id,
                status=FAILURE_HOOK_STATUS_SKIPPED,
                recovered=False,
                authority_result={},
                failure=failure,
                reason="auto_recover_disabled",
            )

        try:
            authority_result = run_recovery_pipeline_and_apply_transition(
                task_runtime=self.task_runtime,
                task=task_payload,
                current_state=state_payload,
                source_failure=failure,
                approval_granted=approval_granted,
                metadata={
                    **meta,
                    "recovery_id": recovery_id,
                    "source_session_id": source_session_id,
                },
                pipeline=self.pipeline,
                allow_terminal_write=allow_terminal_write,
                save=save,
            )
            authority_payload = _as_dict(authority_result)
        except Exception as exc:
            return self._build_result(
                recovery_id=recovery_id,
                source_session_id=source_session_id,
                status=FAILURE_HOOK_STATUS_RECOVERY_FAILED,
                recovered=False,
                authority_result={},
                failure=failure,
                reason=str(exc) or exc.__class__.__name__,
            )

        mapped_status, recovered = _map_authority_status(authority_payload.get("status"))
        patch = copy.deepcopy(
            authority_payload.get("requested_patch")
            if isinstance(authority_payload.get("requested_patch"), dict)
            else {}
        )
        return self._build_result(
            recovery_id=recovery_id,
            source_session_id=source_session_id,
            status=mapped_status,
            recovered=recovered,
            authority_result=authority_payload,
            failure=failure,
            runtime_state_patch=patch,
            reason=str(authority_payload.get("reason") or mapped_status),
        )

    def _build_result(
        self,
        *,
        recovery_id: str,
        source_session_id: str,
        status: str,
        recovered: bool,
        authority_result: dict[str, Any],
        failure: dict[str, Any],
        runtime_state_patch: dict[str, Any] | None = None,
        reason: str = "",
    ) -> RuntimeFailureRecoveryHookResult:
        audit_events = [
            {
                "event_type": "runtime_failure_hook_evaluated",
                "recovery_id": recovery_id,
                "source_session_id": source_session_id,
                "status": status,
                "recovered": recovered,
                "reason": reason,
            }
        ]
        return RuntimeFailureRecoveryHookResult(
            hook_id=build_failure_recovery_hook_id(recovery_id, source_session_id),
            recovery_id=recovery_id,
            source_session_id=source_session_id,
            status=status,
            recovered=recovered,
            authority_result=authority_result,
            failure=failure,
            runtime_state_patch=copy.deepcopy(runtime_state_patch or {}),
            reason=reason,
            audit_events=audit_events,
        )


def handle_runtime_failure_with_recovery(
    *,
    task_runtime: Any,
    task: dict[str, Any],
    current_state: dict[str, Any],
    step: dict[str, Any] | None = None,
    step_result: dict[str, Any] | None = None,
    failure_type: str = "",
    failure_message: str = "",
    approval_granted: bool = False,
    metadata: dict[str, Any] | None = None,
    pipeline: Any | None = None,
    auto_recover: bool = True,
    save: bool = False,
    allow_terminal_write: bool = False,
) -> RuntimeFailureRecoveryHookResult:
    hook = RuntimeFailureRecoveryHook(
        task_runtime=task_runtime,
        pipeline=pipeline,
        auto_recover=auto_recover,
    )
    return hook.handle_failure(
        task=task,
        current_state=current_state,
        step=step,
        step_result=step_result,
        failure_type=failure_type,
        failure_message=failure_message,
        approval_granted=approval_granted,
        metadata=metadata,
        save=save,
        allow_terminal_write=allow_terminal_write,
    )


__all__ = [
    "FAILURE_HOOK_STATUS_RECOVERY_APPLIED",
    "FAILURE_HOOK_STATUS_RECOVERY_BLOCKED",
    "FAILURE_HOOK_STATUS_REVIEW_REQUIRED",
    "FAILURE_HOOK_STATUS_RECOVERY_FAILED",
    "FAILURE_HOOK_STATUS_SKIPPED",
    "RuntimeFailureRecoveryHook",
    "RuntimeFailureRecoveryHookResult",
    "build_failure_recovery_hook_id",
    "handle_runtime_failure_with_recovery",
]
