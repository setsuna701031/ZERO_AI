from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any


class SchedulerEvidenceBoundaryRejected(RuntimeError):
    pass


class SchedulerEvidenceEvent:
    def __init__(
        self,
        event_id: str,
        boundary_id: str,
        scheduler_id: str,
        task_id: str,
        queue_name: str,
        orchestration_phase: str,
        sequence: int,
        reason: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
        created_at: str | None = None,
    ) -> None:
        self._event_id = self._validate_text("event_id", event_id)
        self._boundary_id = self._validate_text("boundary_id", boundary_id)
        self._scheduler_id = self._validate_text("scheduler_id", scheduler_id)
        self._task_id = self._validate_text("task_id", task_id)
        self._queue_name = self._validate_text("queue_name", queue_name)
        self._orchestration_phase = self._validate_text(
            "orchestration_phase",
            orchestration_phase,
        )
        self._sequence = self._validate_sequence(sequence)
        self._reason = copy.deepcopy(reason)
        self._evidence_refs = copy.deepcopy(evidence_refs)
        self._metadata = copy.deepcopy(metadata)
        self._runtime_args = copy.deepcopy(runtime_args)
        self._created_at = (
            created_at
            if created_at is not None
            else datetime.now(timezone.utc).isoformat()
        )

    @property
    def event_id(self) -> str:
        return self._event_id

    @property
    def boundary_id(self) -> str:
        return self._boundary_id

    @property
    def scheduler_id(self) -> str:
        return self._scheduler_id

    @property
    def task_id(self) -> str:
        return self._task_id

    @property
    def queue_name(self) -> str:
        return self._queue_name

    @property
    def orchestration_phase(self) -> str:
        return self._orchestration_phase

    @property
    def reason(self) -> Any:
        return copy.deepcopy(self._reason)

    @property
    def evidence_refs(self) -> Any:
        return copy.deepcopy(self._evidence_refs)

    @property
    def metadata(self) -> Any:
        return copy.deepcopy(self._metadata)

    @property
    def runtime_args(self) -> Any:
        return copy.deepcopy(self._runtime_args)

    @property
    def sequence(self) -> int:
        return self._sequence

    @property
    def created_at(self) -> str:
        return self._created_at

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self._fingerprint_payload(),
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _fingerprint_payload(self) -> dict[str, Any]:
        return {
            "event_id": self._event_id,
            "boundary_id": self._boundary_id,
            "scheduler_id": self._scheduler_id,
            "task_id": self._task_id,
            "queue_name": self._queue_name,
            "orchestration_phase": self._orchestration_phase,
            "reason": self._reason,
            "evidence_refs": self._evidence_refs,
            "metadata": self._metadata,
            "runtime_args": self._runtime_args,
            "sequence": self._sequence,
        }

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise SchedulerEvidenceBoundaryRejected(
                f"scheduler evidence boundary {field_name} is required"
            )

        return value

    def _validate_sequence(self, value: int) -> int:
        if not isinstance(value, int) or value < 1:
            raise SchedulerEvidenceBoundaryRejected(
                "scheduler evidence boundary sequence must be a positive integer"
            )

        return value


class SchedulerEvidenceBoundary:
    def __init__(self, boundary_id: str) -> None:
        self.boundary_id = self._validate_text("boundary_id", boundary_id)
        self._sequence = 0
        self._events: list[SchedulerEvidenceEvent] = []

    def on_task_enqueued(
        self,
        scheduler_id: str,
        task_id: str,
        queue_name: str,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> SchedulerEvidenceEvent:
        return self._record_event(
            orchestration_phase="task_enqueued",
            scheduler_id=scheduler_id,
            task_id=task_id,
            queue_name=queue_name,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def on_task_dequeued(
        self,
        scheduler_id: str,
        task_id: str,
        queue_name: str,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> SchedulerEvidenceEvent:
        return self._record_event(
            orchestration_phase="task_dequeued",
            scheduler_id=scheduler_id,
            task_id=task_id,
            queue_name=queue_name,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def on_task_dispatched(
        self,
        scheduler_id: str,
        task_id: str,
        queue_name: str,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> SchedulerEvidenceEvent:
        return self._record_event(
            orchestration_phase="task_dispatched",
            scheduler_id=scheduler_id,
            task_id=task_id,
            queue_name=queue_name,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def on_task_requeued(
        self,
        scheduler_id: str,
        task_id: str,
        queue_name: str,
        reason: Any,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> SchedulerEvidenceEvent:
        return self._record_event(
            orchestration_phase="task_requeued",
            scheduler_id=scheduler_id,
            task_id=task_id,
            queue_name=queue_name,
            reason=reason,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def on_task_cancelled(
        self,
        scheduler_id: str,
        task_id: str,
        queue_name: str,
        reason: Any,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> SchedulerEvidenceEvent:
        return self._record_event(
            orchestration_phase="task_cancelled",
            scheduler_id=scheduler_id,
            task_id=task_id,
            queue_name=queue_name,
            reason=reason,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def list_events(self) -> list[SchedulerEvidenceEvent]:
        return copy.deepcopy(self._events)

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            {
                "boundary_id": self.boundary_id,
                "event_fingerprints": [
                    event.fingerprint
                    for event in self._events
                ],
            },
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _record_event(
        self,
        orchestration_phase: str,
        scheduler_id: str,
        task_id: str,
        queue_name: str,
        reason: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> SchedulerEvidenceEvent:
        scheduler_id = self._validate_text("scheduler_id", scheduler_id)
        task_id = self._validate_text("task_id", task_id)
        queue_name = self._validate_text("queue_name", queue_name)
        self._sequence += 1
        event = SchedulerEvidenceEvent(
            event_id=self._event_id(
                scheduler_id=scheduler_id,
                orchestration_phase=orchestration_phase,
                task_id=task_id,
                queue_name=queue_name,
                sequence=self._sequence,
            ),
            boundary_id=self.boundary_id,
            scheduler_id=scheduler_id,
            task_id=task_id,
            queue_name=queue_name,
            orchestration_phase=orchestration_phase,
            reason=reason,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
            sequence=self._sequence,
        )
        self._events.append(copy.deepcopy(event))
        return copy.deepcopy(event)

    def _event_id(
        self,
        scheduler_id: str,
        orchestration_phase: str,
        task_id: str,
        queue_name: str,
        sequence: int,
    ) -> str:
        return (
            f"{self.boundary_id}:{scheduler_id}:{orchestration_phase}:"
            f"{task_id}:{queue_name}:{sequence}"
        )

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise SchedulerEvidenceBoundaryRejected(
                f"scheduler evidence boundary {field_name} is required"
            )

        return value


__all__ = [
    "SchedulerEvidenceBoundary",
    "SchedulerEvidenceBoundaryRejected",
    "SchedulerEvidenceEvent",
]
