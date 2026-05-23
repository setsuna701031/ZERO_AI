from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

try:
    from core.runtime.runtime_failure_recovery_hook import (
        FAILURE_HOOK_STATUS_RECOVERY_APPLIED,
        FAILURE_HOOK_STATUS_RECOVERY_BLOCKED,
        FAILURE_HOOK_STATUS_RECOVERY_FAILED,
        FAILURE_HOOK_STATUS_REVIEW_REQUIRED,
        FAILURE_HOOK_STATUS_SKIPPED,
        handle_runtime_failure_with_recovery,
    )
except Exception:
    FAILURE_HOOK_STATUS_RECOVERY_APPLIED = "recovery_applied"
    FAILURE_HOOK_STATUS_RECOVERY_BLOCKED = "recovery_blocked"
    FAILURE_HOOK_STATUS_REVIEW_REQUIRED = "review_required"
    FAILURE_HOOK_STATUS_RECOVERY_FAILED = "recovery_failed"
    FAILURE_HOOK_STATUS_SKIPPED = "skipped"

    def handle_runtime_failure_with_recovery(**kwargs: Any) -> Any:
        raise RuntimeError("runtime_failure_recovery_hook_unavailable")


AUTO_RECOVERY_STATUS_APPLIED = "applied"
AUTO_RECOVERY_STATUS_BLOCKED = "blocked"
AUTO_RECOVERY_STATUS_REVIEW_REQUIRED = "review_required"
AUTO_RECOVERY_STATUS_FAILED = "failed"
AUTO_RECOVERY_STATUS_SKIPPED = "skipped"


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


def _map_hook_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized == FAILURE_HOOK_STATUS_RECOVERY_APPLIED:
        return AUTO_RECOVERY_STATUS_APPLIED
    if normalized == FAILURE_HOOK_STATUS_RECOVERY_BLOCKED:
        return AUTO_RECOVERY_STATUS_BLOCKED
    if normalized == FAILURE_HOOK_STATUS_REVIEW_REQUIRED:
        return AUTO_RECOVERY_STATUS_REVIEW_REQUIRED
    if normalized == FAILURE_HOOK_STATUS_SKIPPED:
        return AUTO_RECOVERY_STATUS_SKIPPED
    return AUTO_RECOVERY_STATUS_FAILED


@dataclass(frozen=True)
class TaskRuntimeFailureAutoRecoveryResult:
    auto_recovery_id: str
    recovery_id: str
    task_id: str
    source_session_id: str
    status: str
    recovered: bool
    original_result: dict[str, Any] = field(default_factory=dict)
    hook_result: dict[str, Any] = field(default_factory=dict)
    runtime_state_patch: dict[str, Any] = field(default_factory=dict)
    final_runtime_state: dict[str, Any] = field(default_factory=dict)
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
            "artifact_type": "task_runtime_failure_auto_recovery_result",
            "auto_recovery_id": self.auto_recovery_id,
            "recovery_id": self.recovery_id,
            "task_id": self.task_id,
            "source_session_id": self.source_session_id,
            "status": self.status,
            "recovered": self.recovered,
            "original_result": copy.deepcopy(self.original_result),
            "hook_result": copy.deepcopy(self.hook_result),
            "runtime_state_patch": copy.deepcopy(self.runtime_state_patch),
            "final_runtime_state": copy.deepcopy(self.final_runtime_state),
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


def build_task_runtime_auto_recovery_id(recovery_id: str, task_id: str = "") -> str:
    seed = {
        "kind": "task_runtime_failure_auto_recovery",
        "recovery_id": str(recovery_id or ""),
        "task_id": str(task_id or ""),
    }
    return "task-runtime-auto-recovery-" + _stable_fingerprint(seed)[:16]


class TaskRuntimeFailureAutoRecoveryBridge:
    """
    Safe auto-recovery bridge for TaskRuntime failure paths.

    This bridge is intentionally external to TaskRuntime's core file. It can be
    called from record_step_failure()/mark_failed() integration points without
    allowing the recovery layer to directly mutate runtime state.
    """

    def __init__(
        self,
        *,
        task_runtime: Any,
        pipeline: Any | None = None,
        enabled: bool = True,
        save: bool = False,
        allow_terminal_write: bool = False,
    ) -> None:
        self.task_runtime = task_runtime
        self.pipeline = pipeline
        self.enabled = bool(enabled)
        self.save = bool(save)
        self.allow_terminal_write = bool(allow_terminal_write)

    def handle_record_step_failure_result(
        self,
        *,
        task: dict[str, Any],
        step: dict[str, Any] | None,
        step_result: dict[str, Any] | None,
        record_result: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        approval_granted: bool = False,
    ) -> TaskRuntimeFailureAutoRecoveryResult:
        return self._handle_task_runtime_failure_result(
            task=task,
            record_result=record_result,
            step=step,
            step_result=step_result,
            failure_type="step_failure",
            failure_message=_text(
                (step_result or {}).get("error") if isinstance(step_result, dict) else "",
                (record_result or {}).get("failure_message") if isinstance(record_result, dict) else "",
                (record_result or {}).get("status") if isinstance(record_result, dict) else "",
                default="step_failure",
            ),
            metadata=metadata,
            approval_granted=approval_granted,
        )

    def handle_mark_failed_result(
        self,
        *,
        task: dict[str, Any],
        mark_failed_result: dict[str, Any],
        failure_type: str = "",
        failure_message: str = "",
        metadata: dict[str, Any] | None = None,
        approval_granted: bool = False,
    ) -> TaskRuntimeFailureAutoRecoveryResult:
        return self._handle_task_runtime_failure_result(
            task=task,
            record_result=mark_failed_result,
            step=None,
            step_result={
                "ok": False,
                "error": _text(
                    failure_message,
                    (mark_failed_result or {}).get("failure_message") if isinstance(mark_failed_result, dict) else "",
                    default="task_failed",
                ),
                "failure_type": _text(
                    failure_type,
                    (mark_failed_result or {}).get("failure_type") if isinstance(mark_failed_result, dict) else "",
                    default="runtime_failure",
                ),
            },
            failure_type=_text(
                failure_type,
                (mark_failed_result or {}).get("failure_type") if isinstance(mark_failed_result, dict) else "",
                default="runtime_failure",
            ),
            failure_message=_text(
                failure_message,
                (mark_failed_result or {}).get("failure_message") if isinstance(mark_failed_result, dict) else "",
                default="task_failed",
            ),
            metadata=metadata,
            approval_granted=approval_granted,
        )

    def _handle_task_runtime_failure_result(
        self,
        *,
        task: dict[str, Any],
        record_result: dict[str, Any],
        step: dict[str, Any] | None,
        step_result: dict[str, Any] | None,
        failure_type: str,
        failure_message: str,
        metadata: dict[str, Any] | None,
        approval_granted: bool,
    ) -> TaskRuntimeFailureAutoRecoveryResult:
        task_payload = copy.deepcopy(task if isinstance(task, dict) else {})
        result_payload = copy.deepcopy(record_result if isinstance(record_result, dict) else {})
        meta = copy.deepcopy(metadata if isinstance(metadata, dict) else {})

        runtime_state = copy.deepcopy(
            result_payload.get("runtime_state")
            if isinstance(result_payload.get("runtime_state"), dict)
            else task_payload.get("runtime_state")
            if isinstance(task_payload.get("runtime_state"), dict)
            else {}
        )

        task_id = _text(runtime_state.get("task_id"), task_payload.get("task_id"), task_payload.get("id"))
        recovery_id = _text(
            meta.get("recovery_id"),
            runtime_state.get("recovery_id"),
            default="runtime-recovery-" + _stable_fingerprint(
                {
                    "task_id": task_id,
                    "runtime_state": runtime_state,
                    "failure_type": failure_type,
                    "failure_message": failure_message,
                }
            )[:12],
        )
        source_session_id = _text(
            meta.get("source_session_id"),
            runtime_state.get("session_id"),
            runtime_state.get("source_session_id"),
        )

        if not self.enabled:
            return self._build_result(
                recovery_id=recovery_id,
                task_id=task_id,
                source_session_id=source_session_id,
                status=AUTO_RECOVERY_STATUS_SKIPPED,
                recovered=False,
                original_result=result_payload,
                hook_result={},
                runtime_state_patch={},
                final_runtime_state=runtime_state,
                reason="task_runtime_auto_recovery_disabled",
            )

        try:
            hook_result = handle_runtime_failure_with_recovery(
                task_runtime=self.task_runtime,
                task=task_payload,
                current_state=runtime_state,
                step=step,
                step_result=step_result,
                failure_type=failure_type,
                failure_message=failure_message,
                approval_granted=approval_granted,
                metadata={
                    **meta,
                    "recovery_id": recovery_id,
                    "source_session_id": source_session_id,
                },
                pipeline=self.pipeline,
                auto_recover=True,
                save=self.save,
                allow_terminal_write=self.allow_terminal_write,
            )
            hook_payload = _as_dict(hook_result)
        except Exception as exc:
            return self._build_result(
                recovery_id=recovery_id,
                task_id=task_id,
                source_session_id=source_session_id,
                status=AUTO_RECOVERY_STATUS_FAILED,
                recovered=False,
                original_result=result_payload,
                hook_result={},
                runtime_state_patch={},
                final_runtime_state=runtime_state,
                reason=str(exc) or exc.__class__.__name__,
            )

        status = _map_hook_status(hook_payload.get("status"))
        recovered = bool(hook_payload.get("recovered"))

        runtime_state_patch = copy.deepcopy(
            hook_payload.get("runtime_state_patch")
            if isinstance(hook_payload.get("runtime_state_patch"), dict)
            else {}
        )
        authority = hook_payload.get("authority_result") if isinstance(hook_payload.get("authority_result"), dict) else {}
        final_state = copy.deepcopy(
            authority.get("applied_state")
            if isinstance(authority.get("applied_state"), dict)
            else runtime_state
        )

        return self._build_result(
            recovery_id=recovery_id,
            task_id=task_id,
            source_session_id=source_session_id,
            status=status,
            recovered=recovered,
            original_result=result_payload,
            hook_result=hook_payload,
            runtime_state_patch=runtime_state_patch,
            final_runtime_state=final_state,
            reason=_text(hook_payload.get("reason"), default=status),
        )

    def _build_result(
        self,
        *,
        recovery_id: str,
        task_id: str,
        source_session_id: str,
        status: str,
        recovered: bool,
        original_result: dict[str, Any],
        hook_result: dict[str, Any],
        runtime_state_patch: dict[str, Any],
        final_runtime_state: dict[str, Any],
        reason: str,
    ) -> TaskRuntimeFailureAutoRecoveryResult:
        return TaskRuntimeFailureAutoRecoveryResult(
            auto_recovery_id=build_task_runtime_auto_recovery_id(recovery_id, task_id),
            recovery_id=recovery_id,
            task_id=task_id,
            source_session_id=source_session_id,
            status=status,
            recovered=recovered,
            original_result=original_result,
            hook_result=hook_result,
            runtime_state_patch=runtime_state_patch,
            final_runtime_state=final_runtime_state,
            reason=reason,
            audit_events=[
                {
                    "event_type": "task_runtime_auto_recovery_evaluated",
                    "recovery_id": recovery_id,
                    "task_id": task_id,
                    "status": status,
                    "recovered": recovered,
                    "reason": reason,
                }
            ],
        )


def auto_recover_record_step_failure_result(
    *,
    task_runtime: Any,
    task: dict[str, Any],
    step: dict[str, Any] | None,
    step_result: dict[str, Any] | None,
    record_result: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    approval_granted: bool = False,
    pipeline: Any | None = None,
    enabled: bool = True,
    save: bool = False,
    allow_terminal_write: bool = False,
) -> TaskRuntimeFailureAutoRecoveryResult:
    bridge = TaskRuntimeFailureAutoRecoveryBridge(
        task_runtime=task_runtime,
        pipeline=pipeline,
        enabled=enabled,
        save=save,
        allow_terminal_write=allow_terminal_write,
    )
    return bridge.handle_record_step_failure_result(
        task=task,
        step=step,
        step_result=step_result,
        record_result=record_result,
        metadata=metadata,
        approval_granted=approval_granted,
    )


def auto_recover_mark_failed_result(
    *,
    task_runtime: Any,
    task: dict[str, Any],
    mark_failed_result: dict[str, Any],
    failure_type: str = "",
    failure_message: str = "",
    metadata: dict[str, Any] | None = None,
    approval_granted: bool = False,
    pipeline: Any | None = None,
    enabled: bool = True,
    save: bool = False,
    allow_terminal_write: bool = False,
) -> TaskRuntimeFailureAutoRecoveryResult:
    bridge = TaskRuntimeFailureAutoRecoveryBridge(
        task_runtime=task_runtime,
        pipeline=pipeline,
        enabled=enabled,
        save=save,
        allow_terminal_write=allow_terminal_write,
    )
    return bridge.handle_mark_failed_result(
        task=task,
        mark_failed_result=mark_failed_result,
        failure_type=failure_type,
        failure_message=failure_message,
        metadata=metadata,
        approval_granted=approval_granted,
    )


__all__ = [
    "AUTO_RECOVERY_STATUS_APPLIED",
    "AUTO_RECOVERY_STATUS_BLOCKED",
    "AUTO_RECOVERY_STATUS_REVIEW_REQUIRED",
    "AUTO_RECOVERY_STATUS_FAILED",
    "AUTO_RECOVERY_STATUS_SKIPPED",
    "TaskRuntimeFailureAutoRecoveryBridge",
    "TaskRuntimeFailureAutoRecoveryResult",
    "auto_recover_mark_failed_result",
    "auto_recover_record_step_failure_result",
    "build_task_runtime_auto_recovery_id",
]
