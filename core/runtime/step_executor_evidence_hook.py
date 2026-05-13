from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any


class StepExecutorEvidenceHookRejected(RuntimeError):
    pass


class StepExecutorEvidenceEvent:
    def __init__(
        self,
        event_id: str,
        hook_id: str,
        phase: str,
        task_id: str,
        step_id: str,
        step_type: str,
        status: str | None = None,
        error: Any = None,
        reason: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
        created_at: str | None = None,
    ) -> None:
        self._event_id = self._validate_text("event_id", event_id)
        self._hook_id = self._validate_text("hook_id", hook_id)
        self._phase = self._validate_text("phase", phase)
        self._task_id = self._validate_text("task_id", task_id)
        self._step_id = self._validate_text("step_id", step_id)
        self._step_type = self._validate_text("step_type", step_type)
        self._status = status
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
    def hook_id(self) -> str:
        return self._hook_id

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def task_id(self) -> str:
        return self._task_id

    @property
    def step_id(self) -> str:
        return self._step_id

    @property
    def step_type(self) -> str:
        return self._step_type

    @property
    def status(self) -> str | None:
        return self._status

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
            "hook_id": self._hook_id,
            "phase": self._phase,
            "task_id": self._task_id,
            "step_id": self._step_id,
            "step_type": self._step_type,
            "status": self._status,
            "error": self._error,
            "reason": self._reason,
            "evidence_refs": self._evidence_refs,
            "metadata": self._metadata,
            "runtime_args": self._runtime_args,
        }

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise StepExecutorEvidenceHookRejected(
                f"step executor evidence hook {field_name} is required"
            )

        return value


class StepExecutorEvidenceHook:
    def __init__(self, hook_id: str) -> None:
        self.hook_id = self._validate_text("hook_id", hook_id)
        self._sequence = 0
        self._events: list[StepExecutorEvidenceEvent] = []

    def before_step(
        self,
        task_id: str,
        step_id: str,
        step_type: str,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> StepExecutorEvidenceEvent:
        return self._record_event(
            phase="before_step",
            task_id=task_id,
            step_id=step_id,
            step_type=step_type,
            status="pending",
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def after_step(
        self,
        task_id: str,
        step_id: str,
        step_type: str,
        status: str,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> StepExecutorEvidenceEvent:
        return self._record_event(
            phase="after_step",
            task_id=task_id,
            step_id=step_id,
            step_type=step_type,
            status=status,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def on_step_failure(
        self,
        task_id: str,
        step_id: str,
        step_type: str,
        error: Any,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> StepExecutorEvidenceEvent:
        return self._record_event(
            phase="step_failure",
            task_id=task_id,
            step_id=step_id,
            step_type=step_type,
            status="failed",
            error=error,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def on_step_blocked(
        self,
        task_id: str,
        step_id: str,
        step_type: str,
        reason: Any,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> StepExecutorEvidenceEvent:
        return self._record_event(
            phase="step_blocked",
            task_id=task_id,
            step_id=step_id,
            step_type=step_type,
            status="blocked",
            reason=reason,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def list_events(self) -> list[StepExecutorEvidenceEvent]:
        return copy.deepcopy(self._events)

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            [
                event.fingerprint
                for event in self._events
            ],
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _record_event(
        self,
        phase: str,
        task_id: str,
        step_id: str,
        step_type: str,
        status: str | None = None,
        error: Any = None,
        reason: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> StepExecutorEvidenceEvent:
        task_id = self._validate_text("task_id", task_id)
        step_id = self._validate_text("step_id", step_id)
        step_type = self._validate_text("step_type", step_type)
        self._sequence += 1
        event = StepExecutorEvidenceEvent(
            event_id=self._event_id(
                phase=phase,
                task_id=task_id,
                step_id=step_id,
                step_type=step_type,
                sequence=self._sequence,
            ),
            hook_id=self.hook_id,
            phase=phase,
            task_id=task_id,
            step_id=step_id,
            step_type=step_type,
            status=status,
            error=error,
            reason=reason,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )
        self._events.append(copy.deepcopy(event))
        return copy.deepcopy(event)

    def _event_id(
        self,
        phase: str,
        task_id: str,
        step_id: str,
        step_type: str,
        sequence: int,
    ) -> str:
        return (
            f"{self.hook_id}:{phase}:{task_id}:{step_id}:"
            f"{step_type}:{sequence}"
        )

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise StepExecutorEvidenceHookRejected(
                f"step executor evidence hook {field_name} is required"
            )

        return value
