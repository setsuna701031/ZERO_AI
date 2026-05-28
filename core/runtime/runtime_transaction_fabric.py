from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


TRANSACTION_STATUS_OPEN = "open"
TRANSACTION_STATUS_PREPARED = "prepared"
TRANSACTION_STATUS_COMMITTED = "committed"
TRANSACTION_STATUS_FAILED = "failed"
TRANSACTION_STATUS_ROLLED_BACK = "rolled_back"
TRANSACTION_STATUS_RECOVERY_QUEUED = "recovery_queued"
TRANSACTION_STATUS_RECOVERED = "recovered"
TRANSACTION_STATUS_ESCALATED = "escalated"

BOUNDARY_STATUS_ACTIVE = "active"
BOUNDARY_STATUS_SEALED = "sealed"
BOUNDARY_STATUS_BROKEN = "broken"
BOUNDARY_STATUS_ROLLED_BACK = "rolled_back"

CONSISTENCY_STATUS_VERIFIED = "verified"
CONSISTENCY_STATUS_MISMATCH = "mismatch"
CONSISTENCY_STATUS_UNKNOWN = "unknown"

TERMINAL_TRANSACTION_STATUSES = {
    TRANSACTION_STATUS_COMMITTED,
    TRANSACTION_STATUS_ROLLED_BACK,
    TRANSACTION_STATUS_ESCALATED,
}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_transaction_fingerprint(value: Any) -> str:
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
class RuntimeTransactionBoundary:
    boundary_id: str
    transaction_id: str
    execution_id: str = ""
    source_session_id: str = ""
    task_id: str = ""
    status: str = BOUNDARY_STATUS_ACTIVE
    before_snapshot: dict[str, Any] = field(default_factory=dict)
    after_snapshot: dict[str, Any] = field(default_factory=dict)
    rollback_snapshot: dict[str, Any] = field(default_factory=dict)
    checkpoint_refs: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "boundary_id": self.boundary_id,
            "transaction_id": self.transaction_id,
            "execution_id": self.execution_id,
            "source_session_id": self.source_session_id,
            "task_id": self.task_id,
            "status": self.status,
            "before_snapshot": copy.deepcopy(self.before_snapshot),
            "after_snapshot": copy.deepcopy(self.after_snapshot),
            "rollback_snapshot": copy.deepcopy(self.rollback_snapshot),
            "checkpoint_refs": copy.deepcopy(self.checkpoint_refs),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeTransactionBoundary":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            boundary_id=str(data.get("boundary_id") or ""),
            transaction_id=str(data.get("transaction_id") or ""),
            execution_id=str(data.get("execution_id") or ""),
            source_session_id=str(data.get("source_session_id") or ""),
            task_id=str(data.get("task_id") or ""),
            status=str(data.get("status") or BOUNDARY_STATUS_ACTIVE),
            before_snapshot=_copy_dict(data.get("before_snapshot")),
            after_snapshot=_copy_dict(data.get("after_snapshot")),
            rollback_snapshot=_copy_dict(data.get("rollback_snapshot")),
            checkpoint_refs=_copy_list(data.get("checkpoint_refs")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeTransactionStep:
    step_id: str
    transaction_id: str
    step_index: int
    action_type: str
    status: str = "pending"
    payload: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    rollback_payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "transaction_id": self.transaction_id,
            "step_index": self.step_index,
            "action_type": self.action_type,
            "status": self.status,
            "payload": copy.deepcopy(self.payload),
            "result": copy.deepcopy(self.result),
            "rollback_payload": copy.deepcopy(self.rollback_payload),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeTransactionStep":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            step_id=str(data.get("step_id") or ""),
            transaction_id=str(data.get("transaction_id") or ""),
            step_index=_safe_int(data.get("step_index"), 0),
            action_type=str(data.get("action_type") or ""),
            status=str(data.get("status") or "pending"),
            payload=_copy_dict(data.get("payload")),
            result=_copy_dict(data.get("result")),
            rollback_payload=_copy_dict(data.get("rollback_payload")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeConsistencyReport:
    report_id: str
    transaction_id: str
    status: str
    expected_fingerprint: str = ""
    actual_fingerprint: str = ""
    verified: bool = False
    reason: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "transaction_id": self.transaction_id,
            "status": self.status,
            "expected_fingerprint": self.expected_fingerprint,
            "actual_fingerprint": self.actual_fingerprint,
            "verified": self.verified,
            "reason": self.reason,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeConsistencyReport":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            report_id=str(data.get("report_id") or ""),
            transaction_id=str(data.get("transaction_id") or ""),
            status=str(data.get("status") or CONSISTENCY_STATUS_UNKNOWN),
            expected_fingerprint=str(data.get("expected_fingerprint") or ""),
            actual_fingerprint=str(data.get("actual_fingerprint") or ""),
            verified=bool(data.get("verified", False)),
            reason=str(data.get("reason") or ""),
            payload=_copy_dict(data.get("payload")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeTransactionRecord:
    transaction_id: str
    source_session_id: str
    execution_id: str = ""
    task_id: str = ""
    status: str = TRANSACTION_STATUS_OPEN
    boundary: RuntimeTransactionBoundary | None = None
    steps: list[RuntimeTransactionStep] = field(default_factory=list)
    recovery_ticket: dict[str, Any] = field(default_factory=dict)
    recovery_result: dict[str, Any] = field(default_factory=dict)
    consistency_report: dict[str, Any] = field(default_factory=dict)
    continuation_ref: dict[str, Any] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "source_session_id": self.source_session_id,
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "status": self.status,
            "boundary": self.boundary.to_dict() if self.boundary is not None else {},
            "steps": [step.to_dict() for step in self.steps],
            "recovery_ticket": copy.deepcopy(self.recovery_ticket),
            "recovery_result": copy.deepcopy(self.recovery_result),
            "consistency_report": copy.deepcopy(self.consistency_report),
            "continuation_ref": copy.deepcopy(self.continuation_ref),
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeTransactionRecord":
        data = payload if isinstance(payload, dict) else {}
        boundary_payload = data.get("boundary")
        boundary = RuntimeTransactionBoundary.from_dict(boundary_payload) if isinstance(boundary_payload, dict) and boundary_payload else None
        steps = []
        for item in data.get("steps") or []:
            if isinstance(item, dict):
                steps.append(RuntimeTransactionStep.from_dict(item))
        return cls(
            transaction_id=str(data.get("transaction_id") or ""),
            source_session_id=str(data.get("source_session_id") or ""),
            execution_id=str(data.get("execution_id") or ""),
            task_id=str(data.get("task_id") or ""),
            status=str(data.get("status") or TRANSACTION_STATUS_OPEN),
            boundary=boundary,
            steps=steps,
            recovery_ticket=_copy_dict(data.get("recovery_ticket")),
            recovery_result=_copy_dict(data.get("recovery_result")),
            consistency_report=_copy_dict(data.get("consistency_report")),
            continuation_ref=_copy_dict(data.get("continuation_ref")),
            payload=_copy_dict(data.get("payload")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeTransactionFabricEvent:
    event_id: str
    event_type: str
    transaction_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "transaction_id": self.transaction_id,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "timestamp": self.timestamp,
            "source": "runtime_transaction_fabric",
        }


class RuntimeTransactionFabricRejected(RuntimeError):
    pass


StepRunner = Callable[[RuntimeTransactionStep, dict[str, Any]], dict[str, Any]]
RollbackRunner = Callable[[RuntimeTransactionStep, dict[str, Any]], dict[str, Any]]


class RuntimeTransactionFabric:
    """
    Transactional consistency layer for the governed runtime.

    Canonical flow:
        begin transaction
          -> create rollback boundary
          -> execute grouped steps
          -> verify consistency
          -> commit

        failure:
          -> seal failed boundary
          -> rollback to before snapshot
          -> queue recovery
          -> consume recovery
          -> transactional continuation
    """

    def __init__(
        self,
        *,
        storage_path: str | Path | None = None,
        recovery_orchestrator: Any = None,
        execution_fabric: Any = None,
        journal: Any = None,
        audit: Any = None,
    ) -> None:
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self.recovery_orchestrator = recovery_orchestrator
        self.execution_fabric = execution_fabric
        self.journal = journal
        self.audit = audit
        self._transactions: dict[str, RuntimeTransactionRecord] = {}
        self._transaction_order: list[str] = []
        self._events: list[RuntimeTransactionFabricEvent] = []
        if self.storage_path is not None:
            self.load()

    @classmethod
    def with_workspace(
        cls,
        workspace_root: str | Path = "workspace",
        **kwargs: Any,
    ) -> "RuntimeTransactionFabric":
        root = Path(workspace_root)
        tx_dir = root / "runtime_transaction_fabric"
        tx_dir.mkdir(parents=True, exist_ok=True)
        return cls(storage_path=tx_dir / "runtime_transaction_fabric.json", **kwargs)

    def begin_transaction(
        self,
        *,
        source_session_id: str,
        execution_id: str = "",
        task_id: str = "",
        before_snapshot: dict[str, Any] | None = None,
        steps: list[dict[str, Any]] | None = None,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        transaction_id: str | None = None,
    ) -> RuntimeTransactionRecord:
        source_session_id = self._validate_text("source_session_id", source_session_id)
        step_payloads = _copy_list(steps)
        if transaction_id is None:
            transaction_id = "runtime-transaction-" + stable_transaction_fingerprint(
                {
                    "source_session_id": source_session_id,
                    "execution_id": execution_id,
                    "task_id": task_id,
                    "steps": step_payloads,
                    "payload": payload or {},
                }
            )[:16]
        transaction_id = self._validate_text("transaction_id", transaction_id)
        if transaction_id in self._transactions:
            raise RuntimeTransactionFabricRejected(f"runtime transaction already exists: {transaction_id!r}")

        boundary_id = "runtime-boundary-" + stable_transaction_fingerprint(
            {"transaction_id": transaction_id, "source_session_id": source_session_id}
        )[:16]
        boundary = RuntimeTransactionBoundary(
            boundary_id=boundary_id,
            transaction_id=transaction_id,
            execution_id=str(execution_id or ""),
            source_session_id=source_session_id,
            task_id=str(task_id or ""),
            before_snapshot=copy.deepcopy(before_snapshot or {}),
            rollback_snapshot=copy.deepcopy(before_snapshot or {}),
        )

        tx_steps = []
        for index, step in enumerate(step_payloads, start=1):
            tx_steps.append(
                RuntimeTransactionStep(
                    step_id="runtime-transaction-step-" + stable_transaction_fingerprint(
                        {
                            "transaction_id": transaction_id,
                            "step_index": index,
                            "step": step,
                        }
                    )[:16],
                    transaction_id=transaction_id,
                    step_index=index,
                    action_type=str(step.get("type") or step.get("action") or "unknown") if isinstance(step, dict) else "unknown",
                    payload=copy.deepcopy(step if isinstance(step, dict) else {"value": step}),
                    rollback_payload=copy.deepcopy((step or {}).get("rollback") if isinstance(step, dict) and isinstance(step.get("rollback"), dict) else {}),
                )
            )

        record = RuntimeTransactionRecord(
            transaction_id=transaction_id,
            source_session_id=source_session_id,
            execution_id=str(execution_id or ""),
            task_id=str(task_id or ""),
            status=TRANSACTION_STATUS_OPEN,
            boundary=boundary,
            steps=tx_steps,
            payload=copy.deepcopy(payload or {}),
            metadata=copy.deepcopy(metadata or {}),
        )
        self._transactions[transaction_id] = record
        self._transaction_order.append(transaction_id)
        self._append_event(
            "runtime_transaction_opened",
            transaction_id=transaction_id,
            payload={"transaction": record.to_dict()},
        )
        self.save()
        return copy.deepcopy(record)

    def prepare_transaction(self, transaction_id: str) -> RuntimeTransactionRecord:
        record = self.get_transaction(transaction_id)
        if record.status != TRANSACTION_STATUS_OPEN:
            raise RuntimeTransactionFabricRejected(f"transaction cannot prepare from status: {record.status!r}")
        updated = self._replace_transaction(record, status=TRANSACTION_STATUS_PREPARED)
        self._append_event(
            "runtime_transaction_prepared",
            transaction_id=transaction_id,
            payload={"transaction": updated.to_dict()},
        )
        self.save()
        return updated

    def execute_transaction(
        self,
        transaction_id: str,
        *,
        runner: StepRunner | None = None,
        context: dict[str, Any] | None = None,
        stop_on_failure: bool = True,
    ) -> RuntimeTransactionRecord:
        record = self.get_transaction(transaction_id)
        if record.status == TRANSACTION_STATUS_OPEN:
            record = self.prepare_transaction(transaction_id)
        if record.status != TRANSACTION_STATUS_PREPARED:
            raise RuntimeTransactionFabricRejected(f"transaction cannot execute from status: {record.status!r}")

        context_payload = copy.deepcopy(context or {})
        completed_steps = []
        failed = False

        for step in record.steps:
            if runner is None:
                result = {"ok": True, "status": "completed", "step_id": step.step_id}
            else:
                result = runner(step, copy.deepcopy(context_payload))
                if not isinstance(result, dict):
                    result = {"ok": True, "result": copy.deepcopy(result)}

            step_failed = bool(result.get("failed", False)) or not bool(result.get("ok", True))
            completed_steps.append(
                RuntimeTransactionStep.from_dict(
                    {
                        **step.to_dict(),
                        "status": "failed" if step_failed else "completed",
                        "result": copy.deepcopy(result),
                        "updated_at": utc_timestamp(),
                    }
                )
            )
            if step_failed:
                failed = True
                if stop_on_failure:
                    remaining = [
                        RuntimeTransactionStep.from_dict(item.to_dict())
                        for item in record.steps[len(completed_steps):]
                    ]
                    completed_steps.extend(remaining)
                    break

        status = TRANSACTION_STATUS_FAILED if failed else TRANSACTION_STATUS_PREPARED
        boundary = record.boundary
        if boundary is not None:
            boundary = RuntimeTransactionBoundary.from_dict(
                {
                    **boundary.to_dict(),
                    "status": BOUNDARY_STATUS_BROKEN if failed else BOUNDARY_STATUS_SEALED,
                    "after_snapshot": {
                        "steps_completed": sum(1 for step in completed_steps if step.status == "completed"),
                        "steps_failed": sum(1 for step in completed_steps if step.status == "failed"),
                    },
                    "updated_at": utc_timestamp(),
                }
            )

        updated = RuntimeTransactionRecord.from_dict(
            {
                **record.to_dict(),
                "status": status,
                "steps": [step.to_dict() for step in completed_steps],
                "boundary": boundary.to_dict() if boundary is not None else {},
                "updated_at": utc_timestamp(),
            }
        )
        self._transactions[transaction_id] = updated
        self._append_event(
            "runtime_transaction_executed",
            transaction_id=transaction_id,
            payload={"transaction": updated.to_dict(), "failed": failed},
        )
        self.save()
        return copy.deepcopy(updated)

    def verify_consistency(
        self,
        transaction_id: str,
        *,
        expected_state: dict[str, Any] | None = None,
        actual_state: dict[str, Any] | None = None,
        reason: str = "",
    ) -> RuntimeConsistencyReport:
        record = self.get_transaction(transaction_id)
        expected = copy.deepcopy(expected_state if expected_state is not None else (record.boundary.before_snapshot if record.boundary else {}))
        actual = copy.deepcopy(actual_state if actual_state is not None else (record.boundary.after_snapshot if record.boundary else {}))
        expected_fp = stable_transaction_fingerprint(expected)
        actual_fp = stable_transaction_fingerprint(actual)
        verified = expected_fp == actual_fp
        report = RuntimeConsistencyReport(
            report_id="runtime-consistency-" + stable_transaction_fingerprint(
                {"transaction_id": transaction_id, "expected": expected_fp, "actual": actual_fp}
            )[:16],
            transaction_id=transaction_id,
            status=CONSISTENCY_STATUS_VERIFIED if verified else CONSISTENCY_STATUS_MISMATCH,
            expected_fingerprint=expected_fp,
            actual_fingerprint=actual_fp,
            verified=verified,
            reason=reason or ("state fingerprints match" if verified else "state fingerprints mismatch"),
            payload={"expected_state": expected, "actual_state": actual},
        )
        updated = RuntimeTransactionRecord.from_dict(
            {
                **record.to_dict(),
                "consistency_report": report.to_dict(),
                "updated_at": utc_timestamp(),
            }
        )
        self._transactions[transaction_id] = updated
        self._append_event(
            "runtime_transaction_consistency_verified",
            transaction_id=transaction_id,
            payload={"report": report.to_dict()},
        )
        self.save()
        return copy.deepcopy(report)

    def commit_transaction(
        self,
        transaction_id: str,
        *,
        expected_state: dict[str, Any] | None = None,
        actual_state: dict[str, Any] | None = None,
        require_consistency: bool = False,
    ) -> RuntimeTransactionRecord:
        record = self.get_transaction(transaction_id)
        if record.status == TRANSACTION_STATUS_FAILED:
            raise RuntimeTransactionFabricRejected("failed transaction must rollback or recover before commit")
        if require_consistency:
            report = self.verify_consistency(
                transaction_id,
                expected_state=expected_state,
                actual_state=actual_state,
            )
            if not report.verified:
                raise RuntimeTransactionFabricRejected("transaction consistency verification failed")

        record = self.get_transaction(transaction_id)
        boundary = record.boundary
        if boundary is not None:
            boundary = RuntimeTransactionBoundary.from_dict(
                {**boundary.to_dict(), "status": BOUNDARY_STATUS_SEALED, "updated_at": utc_timestamp()}
            )
        updated = RuntimeTransactionRecord.from_dict(
            {
                **record.to_dict(),
                "status": TRANSACTION_STATUS_COMMITTED,
                "boundary": boundary.to_dict() if boundary is not None else {},
                "updated_at": utc_timestamp(),
            }
        )
        self._transactions[transaction_id] = updated
        self._append_event(
            "runtime_transaction_committed",
            transaction_id=transaction_id,
            payload={"transaction": updated.to_dict()},
        )
        self.save()
        return copy.deepcopy(updated)

    def rollback_transaction(
        self,
        transaction_id: str,
        *,
        rollback_runner: RollbackRunner | None = None,
        context: dict[str, Any] | None = None,
        reason: str = "",
    ) -> RuntimeTransactionRecord:
        record = self.get_transaction(transaction_id)
        rollback_results = []
        for step in reversed(record.steps):
            if step.status != "completed":
                continue
            if rollback_runner is None:
                result = {"ok": True, "status": "rolled_back", "step_id": step.step_id}
            else:
                result = rollback_runner(step, copy.deepcopy(context or {}))
                if not isinstance(result, dict):
                    result = {"ok": True, "result": copy.deepcopy(result)}
            rollback_results.append({"step_id": step.step_id, "result": result})

        boundary = record.boundary
        if boundary is not None:
            boundary = RuntimeTransactionBoundary.from_dict(
                {
                    **boundary.to_dict(),
                    "status": BOUNDARY_STATUS_ROLLED_BACK,
                    "after_snapshot": copy.deepcopy(boundary.rollback_snapshot),
                    "metadata": {
                        **copy.deepcopy(boundary.metadata),
                        "rollback_reason": reason,
                        "rollback_results": rollback_results,
                    },
                    "updated_at": utc_timestamp(),
                }
            )

        updated = RuntimeTransactionRecord.from_dict(
            {
                **record.to_dict(),
                "status": TRANSACTION_STATUS_ROLLED_BACK,
                "boundary": boundary.to_dict() if boundary is not None else {},
                "updated_at": utc_timestamp(),
            }
        )
        self._transactions[transaction_id] = updated
        self._append_event(
            "runtime_transaction_rolled_back",
            transaction_id=transaction_id,
            payload={"transaction": updated.to_dict(), "rollback_results": rollback_results},
        )
        self.save()
        return copy.deepcopy(updated)

    def create_recovery_incident(
        self,
        transaction_id: str,
        *,
        current_tick: int = 0,
        reason: str = "",
    ) -> dict[str, Any]:
        record = self.get_transaction(transaction_id)
        return {
            "incident_id": "runtime-transaction-incident-" + stable_transaction_fingerprint(
                {
                    "transaction_id": transaction_id,
                    "status": record.status,
                    "reason": reason,
                }
            )[:16],
            "incident_type": "runtime_transaction_failed",
            "source_session_id": record.source_session_id,
            "runtime_session_id": record.source_session_id,
            "task_id": record.task_id,
            "execution_id": record.execution_id,
            "transaction_id": record.transaction_id,
            "current_tick": int(current_tick),
            "event_type": "failure",
            "payload": {
                "reason": reason or "runtime transaction failed",
                "transaction": record.to_dict(),
            },
            "metadata": {},
            "source": "runtime_transaction_fabric",
        }

    def queue_recovery(
        self,
        transaction_id: str,
        *,
        current_tick: int = 0,
        reason: str = "",
    ) -> RuntimeTransactionRecord:
        if self.recovery_orchestrator is None or not hasattr(self.recovery_orchestrator, "submit_incident"):
            raise RuntimeTransactionFabricRejected("runtime_transaction_recovery_orchestrator_required")
        record = self.get_transaction(transaction_id)
        incident = self.create_recovery_incident(
            transaction_id,
            current_tick=current_tick,
            reason=reason,
        )
        ticket = self.recovery_orchestrator.submit_incident(
            incident,
            current_tick=current_tick,
        )
        ticket_payload = ticket.to_dict() if hasattr(ticket, "to_dict") else copy.deepcopy(ticket)
        updated = RuntimeTransactionRecord.from_dict(
            {
                **record.to_dict(),
                "status": TRANSACTION_STATUS_RECOVERY_QUEUED,
                "recovery_ticket": ticket_payload,
                "updated_at": utc_timestamp(),
            }
        )
        self._transactions[transaction_id] = updated
        self._append_event(
            "runtime_transaction_recovery_queued",
            transaction_id=transaction_id,
            payload={"incident": incident, "ticket": ticket_payload},
        )
        self.save()
        return copy.deepcopy(updated)

    def consume_recovery_and_continue(
        self,
        transaction_id: str,
        *,
        current_tick: int = 0,
        limit: int = 10,
    ) -> RuntimeTransactionRecord:
        if self.recovery_orchestrator is None or not hasattr(self.recovery_orchestrator, "consume_ready"):
            raise RuntimeTransactionFabricRejected("runtime_transaction_recovery_orchestrator_required")
        record = self.get_transaction(transaction_id)
        recovery_results = self.recovery_orchestrator.consume_ready(current_tick=current_tick, limit=limit)
        normalized = [
            item.to_dict() if hasattr(item, "to_dict") else copy.deepcopy(item)
            for item in recovery_results
        ]
        matching = None
        recovery_id = str(record.recovery_ticket.get("recovery_id") or "")
        for item in normalized:
            ticket = item.get("ticket") if isinstance(item, dict) else {}
            if isinstance(ticket, dict) and str(ticket.get("recovery_id") or "") == recovery_id:
                matching = item
                break
        if matching is None and normalized:
            matching = normalized[0]
        if matching is None:
            raise RuntimeTransactionFabricRejected("runtime_transaction_recovery_result_not_available")

        continuation_ref = {
            "continuation_id": "runtime-transaction-continuation-" + stable_transaction_fingerprint(
                {"transaction_id": transaction_id, "recovery_id": recovery_id}
            )[:16],
            "transaction_id": transaction_id,
            "source_session_id": record.source_session_id,
            "status": "ready",
            "recovery_result": copy.deepcopy(matching),
            "created_at": utc_timestamp(),
        }

        updated = RuntimeTransactionRecord.from_dict(
            {
                **record.to_dict(),
                "status": TRANSACTION_STATUS_RECOVERED,
                "recovery_result": copy.deepcopy(matching),
                "continuation_ref": continuation_ref,
                "updated_at": utc_timestamp(),
            }
        )
        self._transactions[transaction_id] = updated
        self._append_event(
            "runtime_transaction_recovered",
            transaction_id=transaction_id,
            payload={"transaction": updated.to_dict(), "recovery_result": matching},
        )
        self.save()
        return copy.deepcopy(updated)

    def get_transaction(self, transaction_id: str) -> RuntimeTransactionRecord:
        transaction_id = self._validate_text("transaction_id", transaction_id)
        record = self._transactions.get(transaction_id)
        if record is None:
            raise RuntimeTransactionFabricRejected(f"runtime transaction does not exist: {transaction_id!r}")
        return copy.deepcopy(record)

    def list_transactions(self) -> list[RuntimeTransactionRecord]:
        return [
            copy.deepcopy(self._transactions[transaction_id])
            for transaction_id in self._transaction_order
            if transaction_id in self._transactions
        ]

    def list_events(self) -> list[RuntimeTransactionFabricEvent]:
        return [copy.deepcopy(event) for event in self._events]

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_phase": "runtime_transaction_fabric",
            "transactions": [
                self._transactions[transaction_id].to_dict()
                for transaction_id in self._transaction_order
                if transaction_id in self._transactions
            ],
            "events": [event.to_dict() for event in self._events[-500:]],
        }

    def load(self) -> None:
        if self.storage_path is None:
            return
        if not self.storage_path.exists():
            self._transactions = {}
            self._transaction_order = []
            self._events = []
            return
        payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        self._transactions = {}
        self._transaction_order = []
        self._events = []
        if not isinstance(payload, dict):
            return
        for item in payload.get("transactions") or []:
            if isinstance(item, dict):
                record = RuntimeTransactionRecord.from_dict(item)
                if record.transaction_id:
                    self._transactions[record.transaction_id] = record
                    self._transaction_order.append(record.transaction_id)
        for item in payload.get("events") or []:
            if isinstance(item, dict):
                event = RuntimeTransactionFabricEvent(
                    event_id=str(item.get("event_id") or ""),
                    event_type=str(item.get("event_type") or ""),
                    transaction_id=str(item.get("transaction_id") or ""),
                    payload=_copy_dict(item.get("payload")),
                    metadata=_copy_dict(item.get("metadata")),
                    timestamp=str(item.get("timestamp") or utc_timestamp()),
                )
                if event.event_id:
                    self._events.append(event)

    def save(self) -> None:
        if self.storage_path is None:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _replace_transaction(self, record: RuntimeTransactionRecord, **updates: Any) -> RuntimeTransactionRecord:
        payload = record.to_dict()
        payload.update(copy.deepcopy(updates))
        payload["updated_at"] = utc_timestamp()
        updated = RuntimeTransactionRecord.from_dict(payload)
        self._transactions[updated.transaction_id] = updated
        self.save()
        return copy.deepcopy(updated)

    def _append_event(
        self,
        event_type: str,
        *,
        transaction_id: str = "",
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        event_id = "runtime-transaction-fabric-event-" + stable_transaction_fingerprint(
            {
                "event_type": event_type,
                "transaction_id": transaction_id,
                "sequence": len(self._events) + 1,
            }
        )[:16]
        event = RuntimeTransactionFabricEvent(
            event_id=event_id,
            event_type=event_type,
            transaction_id=str(transaction_id or ""),
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
                    target.append_record("runtime_transaction_fabric", event.to_dict())
            except Exception:
                pass

    def _validate_text(self, field_name: str, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise RuntimeTransactionFabricRejected(f"{field_name}_required")
        return text
