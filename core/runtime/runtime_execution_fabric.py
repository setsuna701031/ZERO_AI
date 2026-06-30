from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from core.goals.goal_lineage_contract import GOAL_LINEAGE_FIELDS, extract_goal_lineage, extract_runtime_identity
from core.runtime.runtime_persistence_service import RuntimePersistenceService
from core.runtime.contracts.runtime_execution_contract import (
    RUNTIME_EXECUTION_SCHEMA,
    normalize_runtime_execution_mode,
)


EXECUTION_STATUS_CREATED = "created"
EXECUTION_STATUS_RUNNING = "running"
EXECUTION_STATUS_CHECKPOINTED = "checkpointed"
EXECUTION_STATUS_COMPLETED = "completed"
EXECUTION_STATUS_FAILED = "failed"
EXECUTION_STATUS_PAUSED = "paused"
EXECUTION_STATUS_RECOVERY_QUEUED = "recovery_queued"
EXECUTION_STATUS_RECOVERED = "recovered"
EXECUTION_STATUS_ESCALATED = "escalated"

CHECKPOINT_TYPE_START = "start"
CHECKPOINT_TYPE_STEP = "step"
CHECKPOINT_TYPE_FAILURE = "failure"
CHECKPOINT_TYPE_RECOVERY = "recovery"
CHECKPOINT_TYPE_COMPLETE = "complete"

TERMINAL_EXECUTION_STATUSES = {
    EXECUTION_STATUS_COMPLETED,
    EXECUTION_STATUS_FAILED,
    EXECUTION_STATUS_ESCALATED,
}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_execution_fabric_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _copy_dict(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _copy_list(value: Any) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


@dataclass(frozen=True)
class RuntimeExecutionCheckpoint:
    checkpoint_id: str
    execution_id: str
    checkpoint_type: str
    status: str
    step_index: int = 0
    source_session_id: str = ""
    task_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    state_snapshot: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    sequence: int = 0
    created_at: str = field(default_factory=utc_timestamp)

    def runtime_execution_validation_summary(
        self,
        record: RuntimeExecutionRecord,
    ) -> dict[str, Any]:
        """Return a passive execution-contract summary.

        This does not validate, reject, checkpoint, recover, or resume anything.
        It only projects the current execution record into the runtime execution
        contract layer for observability.
        """

        metadata = record.metadata if isinstance(record.metadata, dict) else {}
        payload = record.payload if isinstance(record.payload, dict) else {}
        execution_mode = normalize_runtime_execution_mode(
            metadata.get("execution_mode")
            or payload.get("execution_mode")
            or "execute"
        )
        return {
            "schema": RUNTIME_EXECUTION_SCHEMA,
            "execution_id": bool(str(record.execution_id or "").strip()),
            "session_id": bool(str(record.source_session_id or "").strip()),
            "runtime_session_id": bool(
                str(
                    metadata.get("runtime_session_id")
                    or payload.get("runtime_session_id")
                    or ""
                ).strip()
            ),
            "task_id": bool(str(record.task_id or "").strip()),
            "execution_mode": execution_mode,
            "has_payload": bool(payload),
            "has_metadata": bool(metadata),
            "has_authority": bool(
                isinstance(metadata.get("execution_authority"), dict)
                or isinstance(payload.get("execution_authority"), dict)
            ),
            "has_runtime_identity": bool(
                isinstance(metadata.get("runtime_identity"), dict)
                or isinstance(payload.get("runtime_identity"), dict)
            ),
            "has_authority_context": bool(
                isinstance(metadata.get("authority_context"), dict)
                or isinstance(payload.get("authority_context"), dict)
            ),
            "checkpoint_count": len(record.checkpoints),
            "terminal": record.status in TERMINAL_EXECUTION_STATUSES,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "execution_id": self.execution_id,
            "checkpoint_type": self.checkpoint_type,
            "status": self.status,
            "step_index": self.step_index,
            "source_session_id": self.source_session_id,
            "task_id": self.task_id,
            "payload": copy.deepcopy(self.payload),
            "state_snapshot": copy.deepcopy(self.state_snapshot),
            "result": copy.deepcopy(self.result),
            "metadata": copy.deepcopy(self.metadata),
            "sequence": self.sequence,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeExecutionCheckpoint":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            checkpoint_id=str(data.get("checkpoint_id") or ""),
            execution_id=str(data.get("execution_id") or ""),
            checkpoint_type=str(data.get("checkpoint_type") or ""),
            status=str(data.get("status") or EXECUTION_STATUS_CHECKPOINTED),
            step_index=_safe_int(data.get("step_index"), 0),
            source_session_id=str(data.get("source_session_id") or ""),
            task_id=str(data.get("task_id") or ""),
            payload=_copy_dict(data.get("payload")),
            state_snapshot=_copy_dict(data.get("state_snapshot")),
            result=_copy_dict(data.get("result")),
            metadata=_copy_dict(data.get("metadata")),
            sequence=_safe_int(data.get("sequence"), 0),
            created_at=str(data.get("created_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeExecutionRecord:
    execution_id: str
    source_session_id: str
    task_id: str = ""
    status: str = EXECUTION_STATUS_CREATED
    current_step_index: int = 0
    total_steps: int = 0
    checkpoints: list[RuntimeExecutionCheckpoint] = field(default_factory=list)
    recovery_ticket: dict[str, Any] = field(default_factory=dict)
    recovery_result: dict[str, Any] = field(default_factory=dict)
    continuation_ref: dict[str, Any] = field(default_factory=dict)
    replay_ref: dict[str, Any] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "source_session_id": self.source_session_id,
            "task_id": self.task_id,
            "status": self.status,
            "current_step_index": self.current_step_index,
            "total_steps": self.total_steps,
            "checkpoints": [checkpoint.to_dict() for checkpoint in self.checkpoints],
            "recovery_ticket": copy.deepcopy(self.recovery_ticket),
            "recovery_result": copy.deepcopy(self.recovery_result),
            "continuation_ref": copy.deepcopy(self.continuation_ref),
            "replay_ref": copy.deepcopy(self.replay_ref),
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeExecutionRecord":
        data = payload if isinstance(payload, dict) else {}
        checkpoints = []
        for item in data.get("checkpoints") or []:
            if isinstance(item, dict):
                checkpoints.append(RuntimeExecutionCheckpoint.from_dict(item))
        return cls(
            execution_id=str(data.get("execution_id") or ""),
            source_session_id=str(data.get("source_session_id") or ""),
            task_id=str(data.get("task_id") or ""),
            status=str(data.get("status") or EXECUTION_STATUS_CREATED),
            current_step_index=_safe_int(data.get("current_step_index"), 0),
            total_steps=_safe_int(data.get("total_steps"), 0),
            checkpoints=checkpoints,
            recovery_ticket=_copy_dict(data.get("recovery_ticket")),
            recovery_result=_copy_dict(data.get("recovery_result")),
            continuation_ref=_copy_dict(data.get("continuation_ref")),
            replay_ref=_copy_dict(data.get("replay_ref")),
            payload=_copy_dict(data.get("payload")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeExecutionContinuation:
    continuation_id: str
    execution_id: str
    source_session_id: str
    task_id: str = ""
    resume_from_checkpoint_id: str = ""
    resume_step_index: int = 0
    status: str = "ready"
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "continuation_id": self.continuation_id,
            "execution_id": self.execution_id,
            "source_session_id": self.source_session_id,
            "task_id": self.task_id,
            "resume_from_checkpoint_id": self.resume_from_checkpoint_id,
            "resume_step_index": self.resume_step_index,
            "status": self.status,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class RuntimeExecutionFabricEvent:
    event_id: str
    event_type: str
    execution_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "execution_id": self.execution_id,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "timestamp": self.timestamp,
            "source": "runtime_execution_fabric",
        }


class RuntimeExecutionFabricRejected(RuntimeError):
    pass


StepRunner = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


class RuntimeExecutionFabric:
    """
    Governed execution fabric.

    Canonical flow:
        task/session
          -> execution record
          -> start checkpoint
          -> step checkpoint(s)
          -> failure checkpoint
          -> recovery ticket
          -> recovery consume
          -> continuation ref
          -> resumed execution

    This module does not replace StepExecutor or Scheduler. It is the runtime
    persistence and continuation layer around execution.
    """

    def __init__(
        self,
        *,
        storage_path: str | Path | None = None,
        recovery_orchestrator: Any = None,
        supervisor: Any = None,
        replay_engine: Any = None,
        journal: Any = None,
        audit: Any = None,
    ) -> None:
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self.recovery_orchestrator = recovery_orchestrator
        self.supervisor = supervisor
        self.replay_engine = replay_engine
        self.journal = journal
        self.audit = audit
        self.persistence_service = RuntimePersistenceService(
            workspace_root=(self.storage_path.parent if self.storage_path is not None else "workspace"),
            source="runtime_execution_fabric",
        )
        self._executions: dict[str, RuntimeExecutionRecord] = {}
        self._execution_order: list[str] = []
        self._continuations: dict[str, RuntimeExecutionContinuation] = {}
        self._continuation_order: list[str] = []
        self._events: list[RuntimeExecutionFabricEvent] = []
        if self.storage_path is not None:
            self.load()

    @classmethod
    def with_workspace(
        cls,
        workspace_root: str | Path = "workspace",
        **kwargs: Any,
    ) -> "RuntimeExecutionFabric":
        root = Path(workspace_root)
        fabric_dir = root / "runtime_execution_fabric"
        fabric_dir.mkdir(parents=True, exist_ok=True)
        return cls(storage_path=fabric_dir / "runtime_execution_fabric.json", **kwargs)

    def start_execution(
        self,
        *,
        source_session_id: str,
        task_id: str = "",
        steps: list[Any] | None = None,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        execution_id: str | None = None,
    ) -> RuntimeExecutionRecord:
        source_session_id = self._validate_text("source_session_id", source_session_id)
        steps_payload = _copy_list(steps)
        if execution_id is None:
            execution_id = "runtime-execution-" + stable_execution_fabric_fingerprint(
                {
                    "source_session_id": source_session_id,
                    "task_id": task_id,
                    "steps": steps_payload,
                    "payload": payload or {},
                }
            )[:16]
        execution_id = self._validate_text("execution_id", execution_id)
        if execution_id in self._executions:
            raise RuntimeExecutionFabricRejected(f"runtime execution already exists: {execution_id!r}")

        record = RuntimeExecutionRecord(
            execution_id=execution_id,
            source_session_id=source_session_id,
            task_id=str(task_id or ""),
            status=EXECUTION_STATUS_CREATED,
            current_step_index=0,
            total_steps=len(steps_payload),
            payload={
                **copy.deepcopy(payload or {}),
                "steps": steps_payload,
            },
            metadata=copy.deepcopy(metadata or {}),
        )
        self._executions[execution_id] = record
        self._execution_order.append(execution_id)

        record = self.checkpoint(
            execution_id,
            checkpoint_type=CHECKPOINT_TYPE_START,
            status=EXECUTION_STATUS_RUNNING,
            step_index=0,
            state_snapshot={"steps_total": len(steps_payload), "current_step_index": 0},
            metadata={"reason": "execution started"},
        )
        self._append_event(
            "runtime_execution_started",
            execution_id=execution_id,
            payload={"execution": record.to_dict()},
        )
        self.save()
        return copy.deepcopy(record)

    def checkpoint(
        self,
        execution_id: str,
        *,
        checkpoint_type: str,
        status: str,
        step_index: int = 0,
        payload: dict[str, Any] | None = None,
        state_snapshot: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeExecutionRecord:
        record = self.get_execution(execution_id)
        sequence = len(record.checkpoints) + 1
        checkpoint_id = "runtime-checkpoint-" + stable_execution_fabric_fingerprint(
            {
                "execution_id": execution_id,
                "checkpoint_type": checkpoint_type,
                "step_index": step_index,
                "sequence": sequence,
            }
        )[:16]
        checkpoint = RuntimeExecutionCheckpoint(
            checkpoint_id=checkpoint_id,
            execution_id=execution_id,
            checkpoint_type=str(checkpoint_type or CHECKPOINT_TYPE_STEP),
            status=str(status or EXECUTION_STATUS_CHECKPOINTED),
            step_index=int(step_index),
            source_session_id=record.source_session_id,
            task_id=record.task_id,
            payload=copy.deepcopy(payload or {}),
            state_snapshot=copy.deepcopy(state_snapshot or {}),
            result=copy.deepcopy(result or {}),
            metadata=copy.deepcopy(metadata or {}),
            sequence=sequence,
        )

        updated = RuntimeExecutionRecord.from_dict(
            {
                **record.to_dict(),
                "status": status,
                "current_step_index": int(step_index),
                "checkpoints": [item.to_dict() for item in record.checkpoints] + [checkpoint.to_dict()],
                "updated_at": utc_timestamp(),
            }
        )
        self._executions[execution_id] = updated
        self._append_event(
            "runtime_execution_checkpointed",
            execution_id=execution_id,
            payload={"checkpoint": checkpoint.to_dict(), "execution_status": status},
        )
        self.save()
        return copy.deepcopy(updated)

    def record_step_result(
        self,
        execution_id: str,
        *,
        step_index: int,
        step: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        state_snapshot: dict[str, Any] | None = None,
    ) -> RuntimeExecutionRecord:
        result_payload = copy.deepcopy(result or {})
        ok = bool(result_payload.get("ok", True))
        failed = bool(result_payload.get("failed", False)) or not ok
        checkpoint_type = CHECKPOINT_TYPE_FAILURE if failed else CHECKPOINT_TYPE_STEP
        status = EXECUTION_STATUS_FAILED if failed else EXECUTION_STATUS_CHECKPOINTED
        return self.checkpoint(
            execution_id,
            checkpoint_type=checkpoint_type,
            status=status,
            step_index=step_index,
            payload={"step": copy.deepcopy(step or {})},
            state_snapshot=copy.deepcopy(state_snapshot or {}),
            result=result_payload,
            metadata={"step_failed": failed},
        )

    def complete_execution(
        self,
        execution_id: str,
        *,
        result: dict[str, Any] | None = None,
        state_snapshot: dict[str, Any] | None = None,
    ) -> RuntimeExecutionRecord:
        record = self.get_execution(execution_id)
        completed = self.checkpoint(
            execution_id,
            checkpoint_type=CHECKPOINT_TYPE_COMPLETE,
            status=EXECUTION_STATUS_COMPLETED,
            step_index=record.total_steps,
            result=copy.deepcopy(result or {"ok": True}),
            state_snapshot=copy.deepcopy(state_snapshot or {}),
            metadata={"reason": "execution completed"},
        )
        self._append_event(
            "runtime_execution_completed",
            execution_id=execution_id,
            payload={"execution": completed.to_dict()},
        )
        self.save()
        return completed

    def create_recovery_incident(
        self,
        execution_id: str,
        *,
        reason: str = "",
        current_tick: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = self.get_execution(execution_id)
        latest = self.latest_checkpoint(execution_id)
        session_identity = extract_runtime_identity(
            {
                "source_session_id": record.source_session_id,
                "metadata": record.metadata,
            },
            reject_conflicts=True,
        )
        goal_lineage = extract_goal_lineage(record.metadata, reject_conflicts=True)
        incident_id = "runtime-execution-incident-" + stable_execution_fabric_fingerprint(
            {
                "execution_id": execution_id,
                "latest_checkpoint_id": latest.checkpoint_id if latest else "",
                "reason": reason,
            }
        )[:16]
        return {
            "incident_id": incident_id,
            "incident_type": "runtime_execution_failed",
            "source_session_id": record.source_session_id,
            "session_id": session_identity.get("session_id", ""),
            "runtime_session_id": session_identity.get("runtime_session_id", ""),
            **{field: goal_lineage[field] for field in GOAL_LINEAGE_FIELDS if goal_lineage.get(field)},
            "task_id": record.task_id,
            "execution_id": execution_id,
            "current_tick": int(current_tick),
            "event_type": "failure",
            "payload": {
                "reason": reason or "runtime execution failed",
                "execution": record.to_dict(),
                "latest_checkpoint": latest.to_dict() if latest is not None else {},
            },
            "metadata": copy.deepcopy(metadata or {}),
            "source": "runtime_execution_fabric",
        }

    def queue_recovery(
        self,
        execution_id: str,
        *,
        current_tick: int = 0,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeExecutionRecord:
        if self.recovery_orchestrator is None or not hasattr(self.recovery_orchestrator, "submit_incident"):
            raise RuntimeExecutionFabricRejected("runtime_execution_recovery_orchestrator_required")

        incident = self.create_recovery_incident(
            execution_id,
            reason=reason,
            current_tick=current_tick,
            metadata=metadata,
        )
        ticket = self.recovery_orchestrator.submit_incident(
            incident,
            current_tick=current_tick,
        )
        ticket_payload = ticket.to_dict() if hasattr(ticket, "to_dict") else copy.deepcopy(ticket)

        record = self.get_execution(execution_id)
        updated = RuntimeExecutionRecord.from_dict(
            {
                **record.to_dict(),
                "status": EXECUTION_STATUS_RECOVERY_QUEUED,
                "recovery_ticket": ticket_payload,
                "updated_at": utc_timestamp(),
            }
        )
        self._executions[execution_id] = updated
        self._append_event(
            "runtime_execution_recovery_queued",
            execution_id=execution_id,
            payload={"incident": incident, "ticket": ticket_payload},
        )
        self.save()
        return copy.deepcopy(updated)

    def consume_recovery_and_build_continuation(
        self,
        execution_id: str,
        *,
        current_tick: int = 0,
        limit: int = 10,
    ) -> RuntimeExecutionContinuation:
        if self.recovery_orchestrator is None or not hasattr(self.recovery_orchestrator, "consume_ready"):
            raise RuntimeExecutionFabricRejected("runtime_execution_recovery_orchestrator_required")

        record = self.get_execution(execution_id)
        recovery_results = self.recovery_orchestrator.consume_ready(
            current_tick=current_tick,
            limit=limit,
        )
        normalized_results = [
            item.to_dict() if hasattr(item, "to_dict") else copy.deepcopy(item)
            for item in recovery_results
        ]
        matching_result = None
        recovery_id = str(record.recovery_ticket.get("recovery_id") or "")
        for item in normalized_results:
            ticket = item.get("ticket") if isinstance(item, dict) else {}
            if isinstance(ticket, dict) and str(ticket.get("recovery_id") or "") == recovery_id:
                matching_result = item
                break
        if matching_result is None and normalized_results:
            matching_result = normalized_results[0]
        if matching_result is None:
            raise RuntimeExecutionFabricRejected("runtime_execution_recovery_result_not_available")

        latest = self.latest_checkpoint(execution_id)
        resume_step_index = int(latest.step_index if latest is not None else record.current_step_index)
        if latest is not None and latest.checkpoint_type == CHECKPOINT_TYPE_FAILURE:
            resume_step_index = latest.step_index

        continuation_id = "runtime-continuation-" + stable_execution_fabric_fingerprint(
            {
                "execution_id": execution_id,
                "checkpoint_id": latest.checkpoint_id if latest else "",
                "recovery_id": recovery_id,
            }
        )[:16]
        continuation = RuntimeExecutionContinuation(
            continuation_id=continuation_id,
            execution_id=execution_id,
            source_session_id=record.source_session_id,
            task_id=record.task_id,
            resume_from_checkpoint_id=latest.checkpoint_id if latest else "",
            resume_step_index=resume_step_index,
            payload={
                "recovery_result": copy.deepcopy(matching_result),
                "latest_checkpoint": latest.to_dict() if latest else {},
            },
            metadata={"current_tick": int(current_tick)},
        )
        self._continuations[continuation_id] = continuation
        if continuation_id not in self._continuation_order:
            self._continuation_order.append(continuation_id)

        replay_ref = {}
        if isinstance(matching_result, dict):
            recovery_result = matching_result.get("recovery_result")
            if isinstance(recovery_result, dict):
                replay_id = str(recovery_result.get("replay_id") or "")
                if replay_id:
                    replay_ref = {"replay_id": replay_id}

        updated = RuntimeExecutionRecord.from_dict(
            {
                **record.to_dict(),
                "status": EXECUTION_STATUS_RECOVERED,
                "recovery_result": copy.deepcopy(matching_result),
                "continuation_ref": continuation.to_dict(),
                "replay_ref": replay_ref,
                "updated_at": utc_timestamp(),
            }
        )
        self._executions[execution_id] = updated

        self.checkpoint(
            execution_id,
            checkpoint_type=CHECKPOINT_TYPE_RECOVERY,
            status=EXECUTION_STATUS_RECOVERED,
            step_index=resume_step_index,
            state_snapshot={"resume_step_index": resume_step_index},
            result=copy.deepcopy(matching_result),
            metadata={"continuation_id": continuation_id},
        )
        self._append_event(
            "runtime_execution_continuation_created",
            execution_id=execution_id,
            payload={"continuation": continuation.to_dict(), "recovery_result": matching_result},
        )
        self.save()
        return copy.deepcopy(continuation)

    def resume_from_continuation(
        self,
        continuation_id: str,
        *,
        runner: StepRunner | None = None,
        context: dict[str, Any] | None = None,
    ) -> RuntimeExecutionRecord:
        continuation_id = self._validate_text("continuation_id", continuation_id)
        continuation = self._continuations.get(continuation_id)
        if continuation is None:
            raise RuntimeExecutionFabricRejected(f"runtime continuation does not exist: {continuation_id!r}")

        record = self.get_execution(continuation.execution_id)
        steps = record.payload.get("steps")
        if not isinstance(steps, list):
            steps = []

        current_context = copy.deepcopy(context or {})
        current_context["continuation"] = continuation.to_dict()
        current_context["execution_id"] = record.execution_id

        resumed_record = RuntimeExecutionRecord.from_dict(
            {
                **record.to_dict(),
                "status": EXECUTION_STATUS_RUNNING,
                "current_step_index": continuation.resume_step_index,
                "updated_at": utc_timestamp(),
            }
        )
        self._executions[record.execution_id] = resumed_record

        for index in range(continuation.resume_step_index, len(steps)):
            step = steps[index]
            if runner is None:
                step_result = {"ok": True, "status": "completed", "step_index": index}
            else:
                step_result = runner(
                    copy.deepcopy(step if isinstance(step, dict) else {"value": step}),
                    copy.deepcopy(current_context),
                )
            resumed_record = self.record_step_result(
                record.execution_id,
                step_index=index + 1,
                step=step if isinstance(step, dict) else {"value": step},
                result=step_result if isinstance(step_result, dict) else {"ok": True, "result": step_result},
                state_snapshot={"resumed_from": continuation_id, "step_index": index + 1},
            )
            if bool((step_result if isinstance(step_result, dict) else {}).get("failed", False)) or not bool((step_result if isinstance(step_result, dict) else {"ok": True}).get("ok", True)):
                self.save()
                return resumed_record

        completed = self.complete_execution(
            record.execution_id,
            result={"ok": True, "status": "completed", "resumed_from": continuation_id},
            state_snapshot={"resumed_from": continuation_id},
        )
        self._append_event(
            "runtime_execution_resumed_completed",
            execution_id=record.execution_id,
            payload={"continuation": continuation.to_dict(), "execution": completed.to_dict()},
        )
        self.save()
        return completed

    def latest_checkpoint(self, execution_id: str) -> RuntimeExecutionCheckpoint | None:
        record = self.get_execution(execution_id)
        if not record.checkpoints:
            return None
        return copy.deepcopy(record.checkpoints[-1])

    def get_execution(self, execution_id: str) -> RuntimeExecutionRecord:
        execution_id = self._validate_text("execution_id", execution_id)
        record = self._executions.get(execution_id)
        if record is None:
            raise RuntimeExecutionFabricRejected(f"runtime execution does not exist: {execution_id!r}")
        return copy.deepcopy(record)

    def get_continuation(self, continuation_id: str) -> RuntimeExecutionContinuation:
        continuation_id = self._validate_text("continuation_id", continuation_id)
        continuation = self._continuations.get(continuation_id)
        if continuation is None:
            raise RuntimeExecutionFabricRejected(f"runtime continuation does not exist: {continuation_id!r}")
        return copy.deepcopy(continuation)

    def list_executions(self) -> list[RuntimeExecutionRecord]:
        return [
            copy.deepcopy(self._executions[execution_id])
            for execution_id in self._execution_order
            if execution_id in self._executions
        ]

    def list_continuations(self) -> list[RuntimeExecutionContinuation]:
        return [
            copy.deepcopy(self._continuations[continuation_id])
            for continuation_id in self._continuation_order
            if continuation_id in self._continuations
        ]

    def list_events(self) -> list[RuntimeExecutionFabricEvent]:
        return [copy.deepcopy(event) for event in self._events]

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_phase": "runtime_execution_fabric",
            "executions": [
                {
                    **self._executions[execution_id].to_dict(),
                    "execution_validation": self.runtime_execution_validation_summary(
                        self._executions[execution_id]
                    ),
                }
                for execution_id in self._execution_order
                if execution_id in self._executions
            ],
            "continuations": [
                self._continuations[continuation_id].to_dict()
                for continuation_id in self._continuation_order
                if continuation_id in self._continuations
            ],
            "events": [event.to_dict() for event in self._events[-500:]],
        }

    def load(self) -> None:
        if self.storage_path is None:
            return
        if not self.storage_path.exists():
            self._executions = {}
            self._execution_order = []
            self._continuations = {}
            self._continuation_order = []
            self._events = []
            return

        payload = self.persistence_service.read_json(
            self.storage_path,
            default={},
        )
        self._executions = {}
        self._execution_order = []
        self._continuations = {}
        self._continuation_order = []
        self._events = []
        if not isinstance(payload, dict):
            return

        for item in payload.get("executions") or []:
            if isinstance(item, dict):
                record = RuntimeExecutionRecord.from_dict(item)
                if record.execution_id:
                    self._executions[record.execution_id] = record
                    self._execution_order.append(record.execution_id)

        for item in payload.get("continuations") or []:
            if isinstance(item, dict):
                continuation = RuntimeExecutionContinuation(
                    continuation_id=str(item.get("continuation_id") or ""),
                    execution_id=str(item.get("execution_id") or ""),
                    source_session_id=str(item.get("source_session_id") or ""),
                    task_id=str(item.get("task_id") or ""),
                    resume_from_checkpoint_id=str(item.get("resume_from_checkpoint_id") or ""),
                    resume_step_index=_safe_int(item.get("resume_step_index"), 0),
                    status=str(item.get("status") or "ready"),
                    payload=_copy_dict(item.get("payload")),
                    metadata=_copy_dict(item.get("metadata")),
                    created_at=str(item.get("created_at") or utc_timestamp()),
                )
                if continuation.continuation_id:
                    self._continuations[continuation.continuation_id] = continuation
                    self._continuation_order.append(continuation.continuation_id)

        for item in payload.get("events") or []:
            if isinstance(item, dict):
                event = RuntimeExecutionFabricEvent(
                    event_id=str(item.get("event_id") or ""),
                    event_type=str(item.get("event_type") or ""),
                    execution_id=str(item.get("execution_id") or ""),
                    payload=_copy_dict(item.get("payload")),
                    metadata=_copy_dict(item.get("metadata")),
                    timestamp=str(item.get("timestamp") or utc_timestamp()),
                )
                if event.event_id:
                    self._events.append(event)

    def save(self) -> None:
        if self.storage_path is None:
            return
        self.persistence_service.write_json(
            self.storage_path,
            self.to_dict(),
            reason="runtime_execution_fabric_save",
            metadata={"runtime_execution_fabric": True},
        )

    def _append_event(
        self,
        event_type: str,
        *,
        execution_id: str = "",
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        event_id = "runtime-execution-fabric-event-" + stable_execution_fabric_fingerprint(
            {
                "event_type": event_type,
                "execution_id": execution_id,
                "sequence": len(self._events) + 1,
            }
        )[:16]
        event = RuntimeExecutionFabricEvent(
            event_id=event_id,
            event_type=event_type,
            execution_id=str(execution_id or ""),
            payload=copy.deepcopy(payload or {}),
            metadata=copy.deepcopy(metadata or {}),
        )
        self._events.append(event)

        for target in (self.audit, self.journal):
            if target is None:
                continue
            try:
                if hasattr(target, "append"):
                    target.append(event.to_dict())
                elif hasattr(target, "record_event"):
                    target.record_event(event.to_dict())
                elif hasattr(target, "record"):
                    target.record(event.to_dict())
                elif hasattr(target, "append_record"):
                    target.append_record("runtime_execution_fabric", event.to_dict())
            except Exception:
                pass

    def _validate_text(self, field_name: str, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise RuntimeExecutionFabricRejected(f"{field_name}_required")
        return text
