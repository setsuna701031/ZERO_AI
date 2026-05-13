from __future__ import annotations

import hashlib
import json
from typing import Any

from core.runtime.step_executor_evidence_hook import (
    StepExecutorEvidenceEvent,
    StepExecutorEvidenceHook,
)


class StepExecutorEvidenceAdapterRejected(RuntimeError):
    pass


class StepExecutorEvidenceAdapter:
    SUCCEEDED_STATUSES = {"ok", "success", "succeeded"}
    BLOCKED_STATUSES = {"blocked", "denied"}
    FAILED_STATUSES = {"failed", "error", "exception"}

    def __init__(
        self,
        adapter_id: str,
        hook: StepExecutorEvidenceHook,
    ) -> None:
        self.adapter_id = self._validate_text("adapter_id", adapter_id)
        if not isinstance(hook, StepExecutorEvidenceHook):
            raise StepExecutorEvidenceAdapterRejected(
                "step executor evidence adapter requires StepExecutorEvidenceHook"
            )
        self.hook = hook

    def emit_before_step(
        self,
        task_id: str,
        step_id: str,
        step_type: str,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> StepExecutorEvidenceEvent:
        return self.hook.before_step(
            task_id=task_id,
            step_id=step_id,
            step_type=step_type,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def emit_after_step(
        self,
        task_id: str,
        step_id: str,
        step_type: str,
        step_result: Any,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> StepExecutorEvidenceEvent:
        return self.hook.after_step(
            task_id=task_id,
            step_id=step_id,
            step_type=step_type,
            status=self._normalize_status(step_result),
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def emit_failure(
        self,
        task_id: str,
        step_id: str,
        step_type: str,
        error: Any,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> StepExecutorEvidenceEvent:
        return self.hook.on_step_failure(
            task_id=task_id,
            step_id=step_id,
            step_type=step_type,
            error=error,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def emit_blocked(
        self,
        task_id: str,
        step_id: str,
        step_type: str,
        reason: Any,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> StepExecutorEvidenceEvent:
        return self.hook.on_step_blocked(
            task_id=task_id,
            step_id=step_id,
            step_type=step_type,
            reason=reason,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            {
                "adapter_id": self.adapter_id,
                "hook_fingerprint": self.hook.fingerprint,
            },
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _normalize_status(self, step_result: Any) -> str:
        raw_status = self._extract_status(step_result)
        status = str(raw_status or "").strip().lower()
        if status in self.SUCCEEDED_STATUSES:
            return "succeeded"
        if status in self.BLOCKED_STATUSES:
            return "blocked"
        if status in self.FAILED_STATUSES:
            return "failed"

        return "failed"

    def _extract_status(self, step_result: Any) -> Any:
        if isinstance(step_result, str):
            return step_result
        if isinstance(step_result, dict):
            if "status" in step_result:
                return step_result.get("status")
            if "result" in step_result and isinstance(step_result["result"], dict):
                nested = step_result["result"]
                if "status" in nested:
                    return nested.get("status")
            if step_result.get("ok") is True:
                return "ok"
            if step_result.get("ok") is False:
                return "failed"
        return None

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise StepExecutorEvidenceAdapterRejected(
                f"step executor evidence adapter {field_name} is required"
            )

        return value
