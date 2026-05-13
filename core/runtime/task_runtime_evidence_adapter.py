from __future__ import annotations

import hashlib
import json
from typing import Any

from core.runtime.task_runtime_evidence_boundary import (
    TaskRuntimeEvidenceBoundary,
    TaskRuntimeEvidenceEvent,
)


class TaskRuntimeEvidenceAdapterRejected(RuntimeError):
    pass


class TaskRuntimeEvidenceAdapter:
    def __init__(
        self,
        adapter_id: str,
        boundary: TaskRuntimeEvidenceBoundary,
    ) -> None:
        self.adapter_id = self._validate_text("adapter_id", adapter_id)
        if not isinstance(boundary, TaskRuntimeEvidenceBoundary):
            raise TaskRuntimeEvidenceAdapterRejected(
                "task runtime evidence adapter requires TaskRuntimeEvidenceBoundary"
            )
        self.boundary = boundary

    def emit_created(
        self,
        task_id: str,
        runtime_status: str,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> TaskRuntimeEvidenceEvent:
        return self.boundary.on_task_created(
            task_id=task_id,
            runtime_status=runtime_status,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def emit_started(
        self,
        task_id: str,
        runtime_status: str,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> TaskRuntimeEvidenceEvent:
        return self.boundary.on_task_started(
            task_id=task_id,
            runtime_status=runtime_status,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def emit_completed(
        self,
        task_id: str,
        runtime_status: str,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> TaskRuntimeEvidenceEvent:
        return self.boundary.on_task_completed(
            task_id=task_id,
            runtime_status=runtime_status,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def emit_failed(
        self,
        task_id: str,
        runtime_status: str,
        error: Any,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> TaskRuntimeEvidenceEvent:
        return self.boundary.on_task_failed(
            task_id=task_id,
            runtime_status=runtime_status,
            error=error,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def emit_blocked(
        self,
        task_id: str,
        runtime_status: str,
        reason: Any,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> TaskRuntimeEvidenceEvent:
        return self.boundary.on_task_blocked(
            task_id=task_id,
            runtime_status=runtime_status,
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
                "boundary_fingerprint": self.boundary.fingerprint,
            },
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise TaskRuntimeEvidenceAdapterRejected(
                f"task runtime evidence adapter {field_name} is required"
            )

        return value


__all__ = [
    "TaskRuntimeEvidenceAdapter",
    "TaskRuntimeEvidenceAdapterRejected",
]
