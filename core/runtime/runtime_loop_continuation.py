from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

try:
    from core.runtime.runtime_step_executor_native_recovery import (
        NATIVE_HOOK_STATUS_BLOCKED,
        NATIVE_HOOK_STATUS_FAILED,
        NATIVE_HOOK_STATUS_RECOVERED,
        NATIVE_HOOK_STATUS_REVIEW_REQUIRED,
        NATIVE_HOOK_STATUS_SKIPPED,
        handle_step_executor_failure_with_recovery,
    )
except Exception:
    NATIVE_HOOK_STATUS_RECOVERED = "recovered"
    NATIVE_HOOK_STATUS_BLOCKED = "blocked"
    NATIVE_HOOK_STATUS_REVIEW_REQUIRED = "review_required"
    NATIVE_HOOK_STATUS_FAILED = "failed"
    NATIVE_HOOK_STATUS_SKIPPED = "skipped"

    def handle_step_executor_failure_with_recovery(**kwargs):
        raise RuntimeError("step_executor_native_recovery_unavailable")


LOOP_CONTINUATION_STATUS_RESUMED = "resumed"
LOOP_CONTINUATION_STATUS_BLOCKED = "blocked"
LOOP_CONTINUATION_STATUS_REVIEW_REQUIRED = "review_required"
LOOP_CONTINUATION_STATUS_FAILED = "failed"
LOOP_CONTINUATION_STATUS_SKIPPED = "skipped"


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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _next_step_index(state: dict[str, Any]) -> int:
    current = _safe_int(state.get("current_step_index"), 0)
    total = _safe_int(state.get("steps_total"), len(state.get("steps", [])) if isinstance(state.get("steps"), list) else 0)
    if current < 0:
        current = 0
    if total > 0 and current > total:
        current = total
    return current


@dataclass(frozen=True)
class RuntimeLoopContinuationResult:
    continuation_id: str
    recovery_id: str
    task_id: str
    status: str
    resumed: bool
    next_step_index: int
    next_action: str
    native_recovery: dict[str, Any] = field(default_factory=dict)
    resumed_state: dict[str, Any] = field(default_factory=dict)
    loop_patch: dict[str, Any] = field(default_factory=dict)
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
            "artifact_type": "runtime_loop_continuation_result",
            "continuation_id": self.continuation_id,
            "recovery_id": self.recovery_id,
            "task_id": self.task_id,
            "status": self.status,
            "resumed": self.resumed,
            "next_step_index": self.next_step_index,
            "next_action": self.next_action,
            "native_recovery": copy.deepcopy(self.native_recovery),
            "resumed_state": copy.deepcopy(self.resumed_state),
            "loop_patch": copy.deepcopy(self.loop_patch),
            "audit_events": copy.deepcopy(self.audit_events),
            "created_at": self.created_at,
        }
        if include_fingerprint:
            payload["fingerprint"] = self.fingerprint
            payload["verified"] = self.verify()
        return payload

    def verify(self) -> bool:
        return self.fingerprint == _stable_fingerprint(self.to_dict(include_fingerprint=False))


def build_loop_continuation_id(recovery_id: str, task_id: str = "") -> str:
    seed = {
        "kind": "runtime_loop_continuation",
        "recovery_id": str(recovery_id or ""),
        "task_id": str(task_id or ""),
    }
    return "runtime-loop-continuation-" + _stable_fingerprint(seed)[:16]


class RuntimeLoopContinuation:
    """
    Recovery-to-loop continuation bridge.

    This layer does not execute the next step. It only decides whether the loop
    may resume, builds the controlled loop patch, and preserves the authority
    boundary already enforced by the recovery stack.
    """

    def __init__(
        self,
        *,
        task_runtime: Any,
        pipeline: Any | None = None,
        enabled: bool = True,
    ) -> None:
        self.task_runtime = task_runtime
        self.pipeline = pipeline
        self.enabled = bool(enabled)

    def handle_failed_step_and_prepare_resume(
        self,
        *,
        task: dict[str, Any],
        runtime_state: dict[str, Any],
        step: dict[str, Any],
        execution_result: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeLoopContinuationResult:
        task_payload = copy.deepcopy(task if isinstance(task, dict) else {})
        state_payload = copy.deepcopy(runtime_state if isinstance(runtime_state, dict) else {})
        meta = copy.deepcopy(metadata if isinstance(metadata, dict) else {})

        recovery_id = str(meta.get("recovery_id") or "loop-recovery-" + _stable_fingerprint({
            "task": task_payload,
            "state": state_payload,
            "step": step,
            "execution_result": execution_result,
        })[:12])
        task_id = str(task_payload.get("id") or state_payload.get("task_id") or "")

        if not self.enabled:
            return self._build_result(
                recovery_id=recovery_id,
                task_id=task_id,
                status=LOOP_CONTINUATION_STATUS_SKIPPED,
                resumed=False,
                next_step_index=_next_step_index(state_payload),
                next_action="recovery_continuation_disabled",
                native_recovery={},
                resumed_state=state_payload,
                loop_patch={},
            )

        native = handle_step_executor_failure_with_recovery(
            task_runtime=self.task_runtime,
            task=task_payload,
            runtime_state=state_payload,
            step=copy.deepcopy(step if isinstance(step, dict) else {}),
            execution_result=copy.deepcopy(execution_result if isinstance(execution_result, dict) else {}),
            metadata=meta,
            enabled=True,
            pipeline=self.pipeline,
        )
        native_payload = _as_dict(native)

        native_status = str(native_payload.get("status") or "").strip().lower()
        final_state = copy.deepcopy(
            native_payload.get("final_runtime_state")
            if isinstance(native_payload.get("final_runtime_state"), dict)
            else state_payload
        )

        if native_status == NATIVE_HOOK_STATUS_RECOVERED:
            loop_patch = self._build_resume_patch(final_state)
            resumed_state = copy.deepcopy(final_state)
            resumed_state.update(loop_patch)
            return self._build_result(
                recovery_id=recovery_id,
                task_id=task_id,
                status=LOOP_CONTINUATION_STATUS_RESUMED,
                resumed=True,
                next_step_index=_next_step_index(resumed_state),
                next_action="run_next_step",
                native_recovery=native_payload,
                resumed_state=resumed_state,
                loop_patch=loop_patch,
            )

        if native_status == NATIVE_HOOK_STATUS_BLOCKED:
            return self._build_result(
                recovery_id=recovery_id,
                task_id=task_id,
                status=LOOP_CONTINUATION_STATUS_BLOCKED,
                resumed=False,
                next_step_index=_next_step_index(final_state),
                next_action="wait_for_recovery_approval",
                native_recovery=native_payload,
                resumed_state=final_state,
                loop_patch={},
            )

        if native_status == NATIVE_HOOK_STATUS_REVIEW_REQUIRED:
            return self._build_result(
                recovery_id=recovery_id,
                task_id=task_id,
                status=LOOP_CONTINUATION_STATUS_REVIEW_REQUIRED,
                resumed=False,
                next_step_index=_next_step_index(final_state),
                next_action="wait_for_recovery_review",
                native_recovery=native_payload,
                resumed_state=final_state,
                loop_patch={},
            )

        if native_status == NATIVE_HOOK_STATUS_SKIPPED:
            return self._build_result(
                recovery_id=recovery_id,
                task_id=task_id,
                status=LOOP_CONTINUATION_STATUS_SKIPPED,
                resumed=False,
                next_step_index=_next_step_index(final_state),
                next_action="recovery_skipped",
                native_recovery=native_payload,
                resumed_state=final_state,
                loop_patch={},
            )

        return self._build_result(
            recovery_id=recovery_id,
            task_id=task_id,
            status=LOOP_CONTINUATION_STATUS_FAILED,
            resumed=False,
            next_step_index=_next_step_index(final_state),
            next_action="inspect_recovery_failure",
            native_recovery=native_payload,
            resumed_state=final_state,
            loop_patch={},
        )

    def _build_resume_patch(self, state: dict[str, Any]) -> dict[str, Any]:
        next_index = _next_step_index(state)
        return {
            "status": "running",
            "current_step_index": next_index,
            "next_action": "run_next_step",
            "last_decision": "resume_after_recovery",
            "last_decision_reason": "governed_recovery_completed",
            "recovery_loop_continuation": {
                "status": LOOP_CONTINUATION_STATUS_RESUMED,
                "next_step_index": next_index,
                "resumed_at": utc_timestamp(),
            },
        }

    def _build_result(
        self,
        *,
        recovery_id: str,
        task_id: str,
        status: str,
        resumed: bool,
        next_step_index: int,
        next_action: str,
        native_recovery: dict[str, Any],
        resumed_state: dict[str, Any],
        loop_patch: dict[str, Any],
    ) -> RuntimeLoopContinuationResult:
        return RuntimeLoopContinuationResult(
            continuation_id=build_loop_continuation_id(recovery_id, task_id),
            recovery_id=recovery_id,
            task_id=task_id,
            status=status,
            resumed=resumed,
            next_step_index=next_step_index,
            next_action=next_action,
            native_recovery=copy.deepcopy(native_recovery),
            resumed_state=copy.deepcopy(resumed_state),
            loop_patch=copy.deepcopy(loop_patch),
            audit_events=[
                {
                    "event_type": "runtime_loop_continuation_evaluated",
                    "recovery_id": recovery_id,
                    "task_id": task_id,
                    "status": status,
                    "resumed": resumed,
                    "next_action": next_action,
                }
            ],
        )


def prepare_runtime_loop_continuation_after_failure(
    *,
    task_runtime: Any,
    task: dict[str, Any],
    runtime_state: dict[str, Any],
    step: dict[str, Any],
    execution_result: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    pipeline: Any | None = None,
    enabled: bool = True,
) -> RuntimeLoopContinuationResult:
    continuation = RuntimeLoopContinuation(
        task_runtime=task_runtime,
        pipeline=pipeline,
        enabled=enabled,
    )
    return continuation.handle_failed_step_and_prepare_resume(
        task=task,
        runtime_state=runtime_state,
        step=step,
        execution_result=execution_result,
        metadata=metadata,
    )


__all__ = [
    "LOOP_CONTINUATION_STATUS_RESUMED",
    "LOOP_CONTINUATION_STATUS_BLOCKED",
    "LOOP_CONTINUATION_STATUS_REVIEW_REQUIRED",
    "LOOP_CONTINUATION_STATUS_FAILED",
    "LOOP_CONTINUATION_STATUS_SKIPPED",
    "RuntimeLoopContinuation",
    "RuntimeLoopContinuationResult",
    "build_loop_continuation_id",
    "prepare_runtime_loop_continuation_after_failure",
]
