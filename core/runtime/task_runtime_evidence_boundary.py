from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any


class TaskRuntimeEvidenceBoundaryRejected(RuntimeError):
    pass


class TaskRuntimeEvidenceEvent:
    def __init__(
        self,
        event_id: str,
        boundary_id: str,
        phase: str,
        task_id: str,
        runtime_status: str,
        sequence: int,
        error: Any = None,
        reason: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
        created_at: str | None = None,
    ) -> None:
        self._event_id = self._validate_text("event_id", event_id)
        self._boundary_id = self._validate_text("boundary_id", boundary_id)
        self._phase = self._validate_text("phase", phase)
        self._task_id = self._validate_text("task_id", task_id)
        self._runtime_status = self._validate_text("runtime_status", runtime_status)
        self._sequence = self._validate_sequence(sequence)
        self._error = copy.deepcopy(error)
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
    def phase(self) -> str:
        return self._phase

    @property
    def task_id(self) -> str:
        return self._task_id

    @property
    def runtime_status(self) -> str:
        return self._runtime_status

    @property
    def error(self) -> Any:
        return copy.deepcopy(self._error)

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
            "phase": self._phase,
            "task_id": self._task_id,
            "runtime_status": self._runtime_status,
            "error": self._error,
            "reason": self._reason,
            "evidence_refs": self._evidence_refs,
            "metadata": self._metadata,
            "runtime_args": self._runtime_args,
            "sequence": self._sequence,
        }

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise TaskRuntimeEvidenceBoundaryRejected(
                f"task runtime evidence boundary {field_name} is required"
            )

        return value

    def _validate_sequence(self, value: int) -> int:
        if not isinstance(value, int) or value < 1:
            raise TaskRuntimeEvidenceBoundaryRejected(
                "task runtime evidence boundary sequence must be a positive integer"
            )

        return value


class TaskRuntimeEvidenceBoundary:
    def __init__(self, boundary_id: str) -> None:
        self.boundary_id = self._validate_text("boundary_id", boundary_id)
        self._sequence = 0
        self._events: list[TaskRuntimeEvidenceEvent] = []

    def on_task_created(
        self,
        task_id: str,
        runtime_status: str,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> TaskRuntimeEvidenceEvent:
        return self._record_event(
            phase="task_created",
            task_id=task_id,
            runtime_status=runtime_status,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def on_task_started(
        self,
        task_id: str,
        runtime_status: str,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> TaskRuntimeEvidenceEvent:
        return self._record_event(
            phase="task_started",
            task_id=task_id,
            runtime_status=runtime_status,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def on_task_completed(
        self,
        task_id: str,
        runtime_status: str,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> TaskRuntimeEvidenceEvent:
        return self._record_event(
            phase="task_completed",
            task_id=task_id,
            runtime_status=runtime_status,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def on_task_failed(
        self,
        task_id: str,
        runtime_status: str,
        error: Any,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> TaskRuntimeEvidenceEvent:
        return self._record_event(
            phase="task_failed",
            task_id=task_id,
            runtime_status=runtime_status,
            error=error,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def on_task_blocked(
        self,
        task_id: str,
        runtime_status: str,
        reason: Any,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> TaskRuntimeEvidenceEvent:
        return self._record_event(
            phase="task_blocked",
            task_id=task_id,
            runtime_status=runtime_status,
            reason=reason,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def list_events(self) -> list[TaskRuntimeEvidenceEvent]:
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
        phase: str,
        task_id: str,
        runtime_status: str,
        error: Any = None,
        reason: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> TaskRuntimeEvidenceEvent:
        task_id = self._validate_text("task_id", task_id)
        runtime_status = self._validate_text("runtime_status", runtime_status)
        self._sequence += 1
        event = TaskRuntimeEvidenceEvent(
            event_id=self._event_id(
                phase=phase,
                task_id=task_id,
                runtime_status=runtime_status,
                sequence=self._sequence,
            ),
            boundary_id=self.boundary_id,
            phase=phase,
            task_id=task_id,
            runtime_status=runtime_status,
            error=error,
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
        phase: str,
        task_id: str,
        runtime_status: str,
        sequence: int,
    ) -> str:
        return f"{self.boundary_id}:{phase}:{task_id}:{runtime_status}:{sequence}"

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise TaskRuntimeEvidenceBoundaryRejected(
                f"task runtime evidence boundary {field_name} is required"
            )

        return value


__all__ = [
    "TaskRuntimeEvidenceBoundary",
    "TaskRuntimeEvidenceBoundaryRejected",
    "TaskRuntimeEvidenceEvent",
]
