from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

try:
    from core.runtime.runtime_task_failure_auto_recovery import (
        AUTO_RECOVERY_STATUS_APPLIED,
        AUTO_RECOVERY_STATUS_BLOCKED,
        AUTO_RECOVERY_STATUS_FAILED,
        AUTO_RECOVERY_STATUS_REVIEW_REQUIRED,
        AUTO_RECOVERY_STATUS_SKIPPED,
        auto_recover_record_step_failure_result,
    )
except Exception:
    AUTO_RECOVERY_STATUS_APPLIED = "applied"
    AUTO_RECOVERY_STATUS_BLOCKED = "blocked"
    AUTO_RECOVERY_STATUS_REVIEW_REQUIRED = "review_required"
    AUTO_RECOVERY_STATUS_FAILED = "failed"
    AUTO_RECOVERY_STATUS_SKIPPED = "skipped"

    def auto_recover_record_step_failure_result(**kwargs):
        raise RuntimeError("auto_recovery_unavailable")


NATIVE_HOOK_STATUS_RECOVERED = "recovered"
NATIVE_HOOK_STATUS_BLOCKED = "blocked"
NATIVE_HOOK_STATUS_REVIEW_REQUIRED = "review_required"
NATIVE_HOOK_STATUS_FAILED = "failed"
NATIVE_HOOK_STATUS_SKIPPED = "skipped"


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


def _map_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized == AUTO_RECOVERY_STATUS_APPLIED:
        return NATIVE_HOOK_STATUS_RECOVERED
    if normalized == AUTO_RECOVERY_STATUS_BLOCKED:
        return NATIVE_HOOK_STATUS_BLOCKED
    if normalized == AUTO_RECOVERY_STATUS_REVIEW_REQUIRED:
        return NATIVE_HOOK_STATUS_REVIEW_REQUIRED
    if normalized == AUTO_RECOVERY_STATUS_SKIPPED:
        return NATIVE_HOOK_STATUS_SKIPPED
    return NATIVE_HOOK_STATUS_FAILED


@dataclass(frozen=True)
class StepExecutorNativeRecoveryHookResult:
    hook_id: str
    recovery_id: str
    task_id: str
    status: str
    recovered: bool
    execution_result: dict[str, Any] = field(default_factory=dict)
    auto_recovery_result: dict[str, Any] = field(default_factory=dict)
    final_runtime_state: dict[str, Any] = field(default_factory=dict)
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_timestamp)
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.fingerprint:
            object.__setattr__(
                self,
                "fingerprint",
                _stable_fingerprint(self.to_dict(include_fingerprint=False)),
            )

    def to_dict(self, include_fingerprint: bool = True) -> dict[str, Any]:
        payload = {
            "artifact_type": "step_executor_native_recovery_hook_result",
            "hook_id": self.hook_id,
            "recovery_id": self.recovery_id,
            "task_id": self.task_id,
            "status": self.status,
            "recovered": self.recovered,
            "execution_result": copy.deepcopy(self.execution_result),
            "auto_recovery_result": copy.deepcopy(self.auto_recovery_result),
            "final_runtime_state": copy.deepcopy(self.final_runtime_state),
            "audit_events": copy.deepcopy(self.audit_events),
            "created_at": self.created_at,
        }
        if include_fingerprint:
            payload["fingerprint"] = self.fingerprint
            payload["verified"] = self.verify()
        return payload

    def verify(self) -> bool:
        return self.fingerprint == _stable_fingerprint(
            self.to_dict(include_fingerprint=False)
        )


class StepExecutorNativeRecoveryHook:
    def __init__(
        self,
        *,
        task_runtime: Any,
        enabled: bool = True,
        pipeline: Any | None = None,
    ) -> None:
        self.task_runtime = task_runtime
        self.enabled = bool(enabled)
        self.pipeline = pipeline

    def handle_execute_step_failure(
        self,
        *,
        task: dict[str, Any],
        runtime_state: dict[str, Any],
        step: dict[str, Any],
        execution_result: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> StepExecutorNativeRecoveryHookResult:
        recovery_id = (
            (metadata or {}).get("recovery_id")
            or "step-recovery-" + _stable_fingerprint({
                "task": task,
                "step": step,
                "result": execution_result,
            })[:12]
        )

        if not self.enabled:
            return self._build_result(
                recovery_id=recovery_id,
                task_id=str(task.get("id") or ""),
                status=NATIVE_HOOK_STATUS_SKIPPED,
                recovered=False,
                execution_result=execution_result,
                auto_recovery_result={},
                final_runtime_state=runtime_state,
            )

        auto_result = auto_recover_record_step_failure_result(
            task_runtime=self.task_runtime,
            task=task,
            step=step,
            step_result=execution_result,
            record_result={
                "ok": False,
                "status": "failed",
                "runtime_state": copy.deepcopy(runtime_state),
            },
            metadata={
                **dict(metadata or {}),
                "recovery_id": recovery_id,
            },
            pipeline=self.pipeline,
        )

        auto_payload = _as_dict(auto_result)

        authority = auto_payload.get("hook_result", {}).get("authority_result", {})
        final_state = authority.get("applied_state", runtime_state)

        return self._build_result(
            recovery_id=recovery_id,
            task_id=str(task.get("id") or ""),
            status=_map_status(auto_payload.get("status")),
            recovered=bool(auto_payload.get("recovered")),
            execution_result=execution_result,
            auto_recovery_result=auto_payload,
            final_runtime_state=final_state,
        )

    def _build_result(
        self,
        *,
        recovery_id: str,
        task_id: str,
        status: str,
        recovered: bool,
        execution_result: dict[str, Any],
        auto_recovery_result: dict[str, Any],
        final_runtime_state: dict[str, Any],
    ) -> StepExecutorNativeRecoveryHookResult:
        return StepExecutorNativeRecoveryHookResult(
            hook_id="step-native-hook-" + _stable_fingerprint({
                "recovery_id": recovery_id,
                "task_id": task_id,
            })[:12],
            recovery_id=recovery_id,
            task_id=task_id,
            status=status,
            recovered=recovered,
            execution_result=copy.deepcopy(execution_result),
            auto_recovery_result=copy.deepcopy(auto_recovery_result),
            final_runtime_state=copy.deepcopy(final_runtime_state),
            audit_events=[
                {
                    "event_type": "step_executor_native_recovery_hook",
                    "recovery_id": recovery_id,
                    "task_id": task_id,
                    "status": status,
                    "recovered": recovered,
                }
            ],
        )


def handle_step_executor_failure_with_recovery(
    *,
    task_runtime: Any,
    task: dict[str, Any],
    runtime_state: dict[str, Any],
    step: dict[str, Any],
    execution_result: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    enabled: bool = True,
    pipeline: Any | None = None,
) -> StepExecutorNativeRecoveryHookResult:
    hook = StepExecutorNativeRecoveryHook(
        task_runtime=task_runtime,
        enabled=enabled,
        pipeline=pipeline,
    )

    return hook.handle_execute_step_failure(
        task=task,
        runtime_state=runtime_state,
        step=step,
        execution_result=execution_result,
        metadata=metadata,
    )


__all__ = [
    "NATIVE_HOOK_STATUS_RECOVERED",
    "NATIVE_HOOK_STATUS_BLOCKED",
    "NATIVE_HOOK_STATUS_REVIEW_REQUIRED",
    "NATIVE_HOOK_STATUS_FAILED",
    "NATIVE_HOOK_STATUS_SKIPPED",
    "StepExecutorNativeRecoveryHook",
    "StepExecutorNativeRecoveryHookResult",
    "handle_step_executor_failure_with_recovery",
]
