from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.runtime.runtime_persistence_service import RuntimePersistenceService


RECOVERY_TICKET_STATUS_QUEUED = "queued"
RECOVERY_TICKET_STATUS_RUNNING = "running"
RECOVERY_TICKET_STATUS_COMPLETED = "completed"
RECOVERY_TICKET_STATUS_FAILED = "failed"
RECOVERY_TICKET_STATUS_ESCALATED = "escalated"
RECOVERY_TICKET_STATUS_BLOCKED = "blocked"

TERMINAL_RECOVERY_TICKET_STATUSES = {
    RECOVERY_TICKET_STATUS_COMPLETED,
    RECOVERY_TICKET_STATUS_FAILED,
    RECOVERY_TICKET_STATUS_ESCALATED,
    RECOVERY_TICKET_STATUS_BLOCKED,
}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_recovery_queue_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _copy_dict(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


@dataclass(frozen=True)
class RuntimeRecoveryTicket:
    ticket_id: str
    recovery_id: str
    source_session_id: str = ""
    incident_id: str = ""
    task_id: str = ""
    status: str = RECOVERY_TICKET_STATUS_QUEUED
    priority: int = 100
    attempt: int = 0
    max_attempts: int = 3
    next_run_tick: int = 0
    created_tick: int = 0
    updated_tick: int = 0
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "recovery_id": self.recovery_id,
            "source_session_id": self.source_session_id,
            "incident_id": self.incident_id,
            "task_id": self.task_id,
            "status": self.status,
            "priority": self.priority,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "next_run_tick": self.next_run_tick,
            "created_tick": self.created_tick,
            "updated_tick": self.updated_tick,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeRecoveryTicket":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            ticket_id=str(data.get("ticket_id") or ""),
            recovery_id=str(data.get("recovery_id") or ""),
            source_session_id=str(data.get("source_session_id") or ""),
            incident_id=str(data.get("incident_id") or ""),
            task_id=str(data.get("task_id") or ""),
            status=str(data.get("status") or RECOVERY_TICKET_STATUS_QUEUED),
            priority=_safe_int(data.get("priority"), 100),
            attempt=_safe_int(data.get("attempt"), 0),
            max_attempts=_safe_int(data.get("max_attempts"), 3),
            next_run_tick=_safe_int(data.get("next_run_tick"), 0),
            created_tick=_safe_int(data.get("created_tick"), 0),
            updated_tick=_safe_int(data.get("updated_tick"), 0),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
            payload=_copy_dict(data.get("payload")),
            metadata=_copy_dict(data.get("metadata")),
        )


class RuntimeRecoveryQueueRejected(RuntimeError):
    pass


class RuntimeRecoveryQueue:
    """
    Persistent FIFO/priority recovery queue.

    This module is intentionally independent from Scheduler, TaskRuntime, and
    StepExecutor. It only owns recovery tickets and queue persistence.
    """

    def __init__(self, storage_path: str | Path | None = None) -> None:
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self.persistence_service = RuntimePersistenceService(
            workspace_root=(self.storage_path.parent if self.storage_path is not None else "workspace"),
            source="runtime_recovery_queue",
        )
        self._tickets: dict[str, RuntimeRecoveryTicket] = {}
        self._order: list[str] = []
        if self.storage_path is not None:
            self.load()

    def enqueue(
        self,
        *,
        recovery_id: str,
        source_session_id: str = "",
        incident_id: str = "",
        task_id: str = "",
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        priority: int = 100,
        max_attempts: int = 3,
        current_tick: int = 0,
        next_run_tick: int | None = None,
        ticket_id: str | None = None,
    ) -> RuntimeRecoveryTicket:
        recovery_id = self._validate_text("recovery_id", recovery_id)
        if ticket_id is None:
            seed = {
                "recovery_id": recovery_id,
                "source_session_id": source_session_id,
                "incident_id": incident_id,
                "task_id": task_id,
                "payload": payload or {},
                "metadata": metadata or {},
            }
            ticket_id = "recovery-ticket-" + stable_recovery_queue_fingerprint(seed)[:16]
        ticket_id = self._validate_text("ticket_id", ticket_id)

        if ticket_id in self._tickets:
            raise RuntimeRecoveryQueueRejected(f"recovery ticket already exists: {ticket_id!r}")

        ticket = RuntimeRecoveryTicket(
            ticket_id=ticket_id,
            recovery_id=recovery_id,
            source_session_id=str(source_session_id or ""),
            incident_id=str(incident_id or ""),
            task_id=str(task_id or ""),
            priority=int(priority),
            max_attempts=max(1, int(max_attempts)),
            next_run_tick=int(current_tick if next_run_tick is None else next_run_tick),
            created_tick=int(current_tick),
            updated_tick=int(current_tick),
            payload=copy.deepcopy(payload or {}),
            metadata=copy.deepcopy(metadata or {}),
        )
        self._tickets[ticket_id] = ticket
        self._order.append(ticket_id)
        self.save()
        return copy.deepcopy(ticket)

    def peek_ready(self, *, current_tick: int = 0, limit: int = 1) -> list[RuntimeRecoveryTicket]:
        ready: list[RuntimeRecoveryTicket] = []
        for ticket_id in self._order:
            ticket = self._tickets.get(ticket_id)
            if ticket is None:
                continue
            if ticket.status != RECOVERY_TICKET_STATUS_QUEUED:
                continue
            if int(ticket.next_run_tick) > int(current_tick):
                continue
            ready.append(ticket)

        ready.sort(key=lambda item: (item.priority, item.next_run_tick, item.created_tick, item.ticket_id))
        return [copy.deepcopy(item) for item in ready[: max(0, int(limit))]]

    def mark_running(self, ticket_id: str, *, current_tick: int = 0) -> RuntimeRecoveryTicket:
        ticket = self._get_ticket(ticket_id)
        if ticket.status != RECOVERY_TICKET_STATUS_QUEUED:
            raise RuntimeRecoveryQueueRejected(
                f"recovery ticket cannot run from status: {ticket.status!r}"
            )
        updated = self._replace_ticket(
            ticket,
            status=RECOVERY_TICKET_STATUS_RUNNING,
            attempt=ticket.attempt + 1,
            updated_tick=int(current_tick),
            updated_at=utc_timestamp(),
        )
        self.save()
        return copy.deepcopy(updated)

    def mark_completed(self, ticket_id: str, *, current_tick: int = 0, result: Any = None) -> RuntimeRecoveryTicket:
        ticket = self._get_ticket(ticket_id)
        metadata = copy.deepcopy(ticket.metadata)
        metadata["last_result"] = copy.deepcopy(result)
        updated = self._replace_ticket(
            ticket,
            status=RECOVERY_TICKET_STATUS_COMPLETED,
            updated_tick=int(current_tick),
            updated_at=utc_timestamp(),
            metadata=metadata,
        )
        self.save()
        return copy.deepcopy(updated)

    def mark_failed(
        self,
        ticket_id: str,
        *,
        current_tick: int = 0,
        error: Any = None,
        next_run_tick: int | None = None,
    ) -> RuntimeRecoveryTicket:
        ticket = self._get_ticket(ticket_id)
        metadata = copy.deepcopy(ticket.metadata)
        metadata["last_error"] = copy.deepcopy(error)
        exhausted = ticket.attempt >= ticket.max_attempts
        updated = self._replace_ticket(
            ticket,
            status=RECOVERY_TICKET_STATUS_ESCALATED if exhausted else RECOVERY_TICKET_STATUS_QUEUED,
            next_run_tick=int(current_tick if next_run_tick is None else next_run_tick),
            updated_tick=int(current_tick),
            updated_at=utc_timestamp(),
            metadata=metadata,
        )
        self.save()
        return copy.deepcopy(updated)

    def mark_escalated(
        self,
        ticket_id: str,
        *,
        current_tick: int = 0,
        reason: str = "",
        handoff: dict[str, Any] | None = None,
    ) -> RuntimeRecoveryTicket:
        ticket = self._get_ticket(ticket_id)
        metadata = copy.deepcopy(ticket.metadata)
        metadata["escalation_reason"] = str(reason or "")
        if handoff is not None:
            metadata["supervisor_handoff"] = copy.deepcopy(handoff)
        updated = self._replace_ticket(
            ticket,
            status=RECOVERY_TICKET_STATUS_ESCALATED,
            updated_tick=int(current_tick),
            updated_at=utc_timestamp(),
            metadata=metadata,
        )
        self.save()
        return copy.deepcopy(updated)

    def get_ticket(self, ticket_id: str) -> RuntimeRecoveryTicket:
        return copy.deepcopy(self._get_ticket(ticket_id))

    def list_tickets(self, *, include_terminal: bool = True) -> list[RuntimeRecoveryTicket]:
        tickets = []
        for ticket_id in self._order:
            ticket = self._tickets.get(ticket_id)
            if ticket is None:
                continue
            if not include_terminal and ticket.status in TERMINAL_RECOVERY_TICKET_STATUSES:
                continue
            tickets.append(copy.deepcopy(ticket))
        return tickets

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_phase": "runtime_recovery_queue",
            "tickets": [self._tickets[ticket_id].to_dict() for ticket_id in self._order if ticket_id in self._tickets],
        }

    def load(self) -> None:
        if self.storage_path is None:
            return
        if not self.storage_path.exists():
            self._tickets = {}
            self._order = []
            return
        payload = self.persistence_service.read_json(
            self.storage_path,
            default={},
        )
        tickets = payload.get("tickets") if isinstance(payload, dict) else []
        self._tickets = {}
        self._order = []
        if isinstance(tickets, list):
            for item in tickets:
                if not isinstance(item, dict):
                    continue
                ticket = RuntimeRecoveryTicket.from_dict(item)
                if not ticket.ticket_id:
                    continue
                self._tickets[ticket.ticket_id] = ticket
                self._order.append(ticket.ticket_id)

    def save(self) -> None:
        if self.storage_path is None:
            return
        self.persistence_service.write_json(
            self.storage_path,
            self.to_dict(),
            reason="runtime_recovery_queue_save",
            metadata={"runtime_recovery_queue": True},
        )

    def _get_ticket(self, ticket_id: str) -> RuntimeRecoveryTicket:
        ticket_id = self._validate_text("ticket_id", ticket_id)
        ticket = self._tickets.get(ticket_id)
        if ticket is None:
            raise RuntimeRecoveryQueueRejected(f"recovery ticket does not exist: {ticket_id!r}")
        return ticket

    def _replace_ticket(self, ticket: RuntimeRecoveryTicket, **updates: Any) -> RuntimeRecoveryTicket:
        payload = ticket.to_dict()
        payload.update(updates)
        updated = RuntimeRecoveryTicket.from_dict(payload)
        self._tickets[updated.ticket_id] = updated
        return updated

    def _validate_text(self, field_name: str, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise RuntimeRecoveryQueueRejected(f"{field_name}_required")
        return text
