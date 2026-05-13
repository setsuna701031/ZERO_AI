from __future__ import annotations

import hashlib
import json
from typing import Any

from core.runtime.scheduler_evidence_boundary import (
    SchedulerEvidenceBoundary,
    SchedulerEvidenceEvent,
)


class SchedulerEvidenceAdapterRejected(RuntimeError):
    pass


class SchedulerEvidenceAdapter:
    def __init__(
        self,
        adapter_id: str,
        boundary: SchedulerEvidenceBoundary,
    ) -> None:
        self.adapter_id = self._validate_text("adapter_id", adapter_id)
        if not isinstance(boundary, SchedulerEvidenceBoundary):
            raise SchedulerEvidenceAdapterRejected(
                "scheduler evidence adapter requires SchedulerEvidenceBoundary"
            )
        self.boundary = boundary

    def emit_enqueued(
        self,
        scheduler_id: str,
        task_id: str,
        queue_name: str,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> SchedulerEvidenceEvent:
        return self.boundary.on_task_enqueued(
            scheduler_id=scheduler_id,
            task_id=task_id,
            queue_name=queue_name,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def emit_dequeued(
        self,
        scheduler_id: str,
        task_id: str,
        queue_name: str,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> SchedulerEvidenceEvent:
        return self.boundary.on_task_dequeued(
            scheduler_id=scheduler_id,
            task_id=task_id,
            queue_name=queue_name,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def emit_dispatched(
        self,
        scheduler_id: str,
        task_id: str,
        queue_name: str,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> SchedulerEvidenceEvent:
        return self.boundary.on_task_dispatched(
            scheduler_id=scheduler_id,
            task_id=task_id,
            queue_name=queue_name,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def emit_requeued(
        self,
        scheduler_id: str,
        task_id: str,
        queue_name: str,
        reason: Any,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> SchedulerEvidenceEvent:
        return self.boundary.on_task_requeued(
            scheduler_id=scheduler_id,
            task_id=task_id,
            queue_name=queue_name,
            reason=reason,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def emit_cancelled(
        self,
        scheduler_id: str,
        task_id: str,
        queue_name: str,
        reason: Any,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> SchedulerEvidenceEvent:
        return self.boundary.on_task_cancelled(
            scheduler_id=scheduler_id,
            task_id=task_id,
            queue_name=queue_name,
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
            raise SchedulerEvidenceAdapterRejected(
                f"scheduler evidence adapter {field_name} is required"
            )

        return value


__all__ = [
    "SchedulerEvidenceAdapter",
    "SchedulerEvidenceAdapterRejected",
]
