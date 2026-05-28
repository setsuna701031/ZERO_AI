from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUPERVISOR_HANDOFF_STATUS_OPEN = "open"
SUPERVISOR_HANDOFF_STATUS_ACKNOWLEDGED = "acknowledged"
SUPERVISOR_HANDOFF_STATUS_RESOLVED = "resolved"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_supervisor_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeSupervisorHandoff:
    handoff_id: str
    recovery_id: str
    ticket_id: str = ""
    source_session_id: str = ""
    incident_id: str = ""
    task_id: str = ""
    reason: str = ""
    status: str = SUPERVISOR_HANDOFF_STATUS_OPEN
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "handoff_id": self.handoff_id,
            "recovery_id": self.recovery_id,
            "ticket_id": self.ticket_id,
            "source_session_id": self.source_session_id,
            "incident_id": self.incident_id,
            "task_id": self.task_id,
            "reason": self.reason,
            "status": self.status,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeSupervisorHandoff":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            handoff_id=str(data.get("handoff_id") or ""),
            recovery_id=str(data.get("recovery_id") or ""),
            ticket_id=str(data.get("ticket_id") or ""),
            source_session_id=str(data.get("source_session_id") or ""),
            incident_id=str(data.get("incident_id") or ""),
            task_id=str(data.get("task_id") or ""),
            reason=str(data.get("reason") or ""),
            status=str(data.get("status") or SUPERVISOR_HANDOFF_STATUS_OPEN),
            payload=copy.deepcopy(data.get("payload") if isinstance(data.get("payload"), dict) else {}),
            metadata=copy.deepcopy(data.get("metadata") if isinstance(data.get("metadata"), dict) else {}),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        )


class RuntimeRecoverySupervisorRejected(RuntimeError):
    pass


class RuntimeRecoverySupervisor:
    """
    Explicit supervisor handoff registry.

    This is not UI. It is a persisted runtime escalation surface that can be
    consumed later by CLI, operator UI, or another runtime supervisor.
    """

    def __init__(self, storage_path: str | Path | None = None) -> None:
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self._handoffs: dict[str, RuntimeSupervisorHandoff] = {}
        self._order: list[str] = []
        if self.storage_path is not None:
            self.load()

    def escalate(
        self,
        *,
        recovery_id: str,
        ticket_id: str = "",
        source_session_id: str = "",
        incident_id: str = "",
        task_id: str = "",
        reason: str = "",
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        handoff_id: str | None = None,
    ) -> RuntimeSupervisorHandoff:
        recovery_id = self._validate_text("recovery_id", recovery_id)
        if handoff_id is None:
            handoff_id = "runtime-supervisor-handoff-" + stable_supervisor_fingerprint(
                {
                    "recovery_id": recovery_id,
                    "ticket_id": ticket_id,
                    "source_session_id": source_session_id,
                    "incident_id": incident_id,
                    "task_id": task_id,
                    "reason": reason,
                }
            )[:16]
        handoff_id = self._validate_text("handoff_id", handoff_id)

        existing = self._handoffs.get(handoff_id)
        if existing is not None:
            return copy.deepcopy(existing)

        handoff = RuntimeSupervisorHandoff(
            handoff_id=handoff_id,
            recovery_id=recovery_id,
            ticket_id=str(ticket_id or ""),
            source_session_id=str(source_session_id or ""),
            incident_id=str(incident_id or ""),
            task_id=str(task_id or ""),
            reason=str(reason or "runtime recovery escalated"),
            payload=copy.deepcopy(payload or {}),
            metadata=copy.deepcopy(metadata or {}),
        )
        self._handoffs[handoff_id] = handoff
        self._order.append(handoff_id)
        self.save()
        return copy.deepcopy(handoff)

    def acknowledge(self, handoff_id: str, *, metadata: dict[str, Any] | None = None) -> RuntimeSupervisorHandoff:
        return self._set_status(
            handoff_id,
            status=SUPERVISOR_HANDOFF_STATUS_ACKNOWLEDGED,
            metadata=metadata,
        )

    def resolve(self, handoff_id: str, *, metadata: dict[str, Any] | None = None) -> RuntimeSupervisorHandoff:
        return self._set_status(
            handoff_id,
            status=SUPERVISOR_HANDOFF_STATUS_RESOLVED,
            metadata=metadata,
        )

    def get_handoff(self, handoff_id: str) -> RuntimeSupervisorHandoff:
        handoff_id = self._validate_text("handoff_id", handoff_id)
        handoff = self._handoffs.get(handoff_id)
        if handoff is None:
            raise RuntimeRecoverySupervisorRejected(f"supervisor handoff does not exist: {handoff_id!r}")
        return copy.deepcopy(handoff)

    def list_handoffs(self, *, status: str | None = None) -> list[RuntimeSupervisorHandoff]:
        result = []
        for handoff_id in self._order:
            handoff = self._handoffs.get(handoff_id)
            if handoff is None:
                continue
            if status is not None and handoff.status != status:
                continue
            result.append(copy.deepcopy(handoff))
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_phase": "runtime_recovery_supervisor",
            "handoffs": [
                self._handoffs[handoff_id].to_dict()
                for handoff_id in self._order
                if handoff_id in self._handoffs
            ],
        }

    def load(self) -> None:
        if self.storage_path is None:
            return
        if not self.storage_path.exists():
            self._handoffs = {}
            self._order = []
            return
        payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        handoffs = payload.get("handoffs") if isinstance(payload, dict) else []
        self._handoffs = {}
        self._order = []
        if isinstance(handoffs, list):
            for item in handoffs:
                if not isinstance(item, dict):
                    continue
                handoff = RuntimeSupervisorHandoff.from_dict(item)
                if handoff.handoff_id:
                    self._handoffs[handoff.handoff_id] = handoff
                    self._order.append(handoff.handoff_id)

    def save(self) -> None:
        if self.storage_path is None:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _set_status(
        self,
        handoff_id: str,
        *,
        status: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeSupervisorHandoff:
        handoff = self.get_handoff(handoff_id)
        merged_metadata = copy.deepcopy(handoff.metadata)
        if metadata:
            merged_metadata.update(copy.deepcopy(metadata))
        updated = RuntimeSupervisorHandoff.from_dict(
            {
                **handoff.to_dict(),
                "status": status,
                "metadata": merged_metadata,
                "updated_at": utc_timestamp(),
            }
        )
        self._handoffs[handoff_id] = updated
        self.save()
        return copy.deepcopy(updated)

    def _validate_text(self, field_name: str, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise RuntimeRecoverySupervisorRejected(f"{field_name}_required")
        return text
