from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WATCHDOG_SESSION_STATUS_HEALTHY = "healthy"
WATCHDOG_SESSION_STATUS_STALLED = "stalled"
WATCHDOG_SESSION_STATUS_DEAD = "dead"
WATCHDOG_SESSION_STATUS_FROZEN = "frozen"
WATCHDOG_SESSION_STATUS_UNKNOWN = "unknown"

WATCHDOG_INCIDENT_TYPE_STALLED = "runtime_session_stalled"
WATCHDOG_INCIDENT_TYPE_DEAD = "runtime_session_dead"
WATCHDOG_INCIDENT_TYPE_FROZEN = "runtime_session_frozen"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_watchdog_fingerprint(value: Any) -> str:
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
class RuntimeHeartbeat:
    session_id: str
    status: str = "running"
    tick: int = 0
    task_id: str = ""
    source: str = "runtime_watchdog"
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "tick": self.tick,
            "task_id": self.task_id,
            "source": self.source,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeHeartbeat":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            session_id=str(data.get("session_id") or ""),
            status=str(data.get("status") or "running"),
            tick=_safe_int(data.get("tick"), 0),
            task_id=str(data.get("task_id") or ""),
            source=str(data.get("source") or "runtime_watchdog"),
            payload=_copy_dict(data.get("payload")),
            metadata=_copy_dict(data.get("metadata")),
            timestamp=str(data.get("timestamp") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeWatchdogSession:
    session_id: str
    task_id: str = ""
    status: str = WATCHDOG_SESSION_STATUS_UNKNOWN
    first_tick: int = 0
    last_heartbeat_tick: int = 0
    last_observed_tick: int = 0
    heartbeat_count: int = 0
    frozen: bool = False
    terminal: bool = False
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "task_id": self.task_id,
            "status": self.status,
            "first_tick": self.first_tick,
            "last_heartbeat_tick": self.last_heartbeat_tick,
            "last_observed_tick": self.last_observed_tick,
            "heartbeat_count": self.heartbeat_count,
            "frozen": self.frozen,
            "terminal": self.terminal,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeWatchdogSession":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            session_id=str(data.get("session_id") or ""),
            task_id=str(data.get("task_id") or ""),
            status=str(data.get("status") or WATCHDOG_SESSION_STATUS_UNKNOWN),
            first_tick=_safe_int(data.get("first_tick"), 0),
            last_heartbeat_tick=_safe_int(data.get("last_heartbeat_tick"), 0),
            last_observed_tick=_safe_int(data.get("last_observed_tick"), 0),
            heartbeat_count=_safe_int(data.get("heartbeat_count"), 0),
            frozen=bool(data.get("frozen", False)),
            terminal=bool(data.get("terminal", False)),
            payload=_copy_dict(data.get("payload")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeWatchdogIncident:
    incident_id: str
    incident_type: str
    session_id: str
    task_id: str = ""
    current_tick: int = 0
    last_heartbeat_tick: int = 0
    status: str = "open"
    source: str = "runtime_watchdog"
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "incident_type": self.incident_type,
            "session_id": self.session_id,
            "source_session_id": self.session_id,
            "runtime_session_id": self.session_id,
            "task_id": self.task_id,
            "current_tick": self.current_tick,
            "last_heartbeat_tick": self.last_heartbeat_tick,
            "status": self.status,
            "source": self.source,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "event_type": "failure",
        }


class RuntimeWatchdogRejected(RuntimeError):
    pass


class RuntimeWatchdog:
    """
    Persistent runtime watchdog.

    Responsibilities:
    - track runtime heartbeats
    - detect stalled/dead/frozen sessions
    - emit runtime incidents
    - optionally submit incidents to RuntimeRecoveryOrchestrator

    Non-responsibilities:
    - no Scheduler branching
    - no StepExecutor execution
    - no recovery execution policy
    """

    TERMINAL_STATUSES = {"finished", "completed", "failed", "cancelled", "timeout", "dead"}

    def __init__(
        self,
        *,
        storage_path: str | Path | None = None,
        stall_after_ticks: int = 3,
        dead_after_ticks: int = 10,
        orchestrator: Any = None,
        journal: Any = None,
        audit: Any = None,
    ) -> None:
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self.stall_after_ticks = max(1, int(stall_after_ticks))
        self.dead_after_ticks = max(self.stall_after_ticks + 1, int(dead_after_ticks))
        self.orchestrator = orchestrator
        self.journal = journal
        self.audit = audit
        self._sessions: dict[str, RuntimeWatchdogSession] = {}
        self._heartbeats: list[RuntimeHeartbeat] = []
        self._incidents: dict[str, RuntimeWatchdogIncident] = {}
        self._incident_order: list[str] = []
        if self.storage_path is not None:
            self.load()

    @classmethod
    def with_workspace(
        cls,
        workspace_root: str | Path = "workspace",
        **kwargs: Any,
    ) -> "RuntimeWatchdog":
        root = Path(workspace_root)
        watchdog_dir = root / "runtime_watchdog"
        watchdog_dir.mkdir(parents=True, exist_ok=True)
        return cls(storage_path=watchdog_dir / "runtime_watchdog.json", **kwargs)

    def register_session(
        self,
        session_id: str,
        *,
        task_id: str = "",
        current_tick: int = 0,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeWatchdogSession:
        session_id = self._validate_text("session_id", session_id)
        existing = self._sessions.get(session_id)
        if existing is not None:
            merged_metadata = copy.deepcopy(existing.metadata)
            if metadata:
                merged_metadata.update(copy.deepcopy(metadata))
            session = RuntimeWatchdogSession.from_dict(
                {
                    **existing.to_dict(),
                    "task_id": task_id or existing.task_id,
                    "last_observed_tick": int(current_tick),
                    "payload": copy.deepcopy(payload or existing.payload),
                    "metadata": merged_metadata,
                    "updated_at": utc_timestamp(),
                }
            )
        else:
            session = RuntimeWatchdogSession(
                session_id=session_id,
                task_id=str(task_id or ""),
                status=WATCHDOG_SESSION_STATUS_HEALTHY,
                first_tick=int(current_tick),
                last_heartbeat_tick=int(current_tick),
                last_observed_tick=int(current_tick),
                heartbeat_count=0,
                payload=copy.deepcopy(payload or {}),
                metadata=copy.deepcopy(metadata or {}),
            )
        self._sessions[session_id] = session
        self.save()
        self._record_event(
            "runtime_watchdog_session_registered",
            {"session": session.to_dict()},
        )
        return copy.deepcopy(session)

    def heartbeat(
        self,
        session_id: str,
        *,
        task_id: str = "",
        status: str = "running",
        current_tick: int = 0,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeHeartbeat:
        session_id = self._validate_text("session_id", session_id)
        if session_id not in self._sessions:
            self.register_session(
                session_id,
                task_id=task_id,
                current_tick=current_tick,
                payload=payload,
                metadata=metadata,
            )

        heartbeat = RuntimeHeartbeat(
            session_id=session_id,
            status=str(status or "running"),
            tick=int(current_tick),
            task_id=str(task_id or self._sessions[session_id].task_id or ""),
            payload=copy.deepcopy(payload or {}),
            metadata=copy.deepcopy(metadata or {}),
        )
        self._heartbeats.append(heartbeat)

        terminal = str(status or "").strip().lower() in self.TERMINAL_STATUSES
        frozen = bool((metadata or {}).get("frozen") or (payload or {}).get("runtime_frozen"))
        session_status = WATCHDOG_SESSION_STATUS_FROZEN if frozen else WATCHDOG_SESSION_STATUS_HEALTHY
        if terminal:
            session_status = str(status or "finished").strip().lower()

        old = self._sessions[session_id]
        merged_metadata = copy.deepcopy(old.metadata)
        if metadata:
            merged_metadata.update(copy.deepcopy(metadata))
        updated = RuntimeWatchdogSession.from_dict(
            {
                **old.to_dict(),
                "task_id": heartbeat.task_id or old.task_id,
                "status": session_status,
                "last_heartbeat_tick": int(current_tick),
                "last_observed_tick": int(current_tick),
                "heartbeat_count": old.heartbeat_count + 1,
                "frozen": frozen,
                "terminal": terminal,
                "payload": copy.deepcopy(payload or old.payload),
                "metadata": merged_metadata,
                "updated_at": utc_timestamp(),
            }
        )
        self._sessions[session_id] = updated
        self.save()
        self._record_event(
            "runtime_watchdog_heartbeat",
            {"heartbeat": heartbeat.to_dict(), "session": updated.to_dict()},
        )
        return copy.deepcopy(heartbeat)

    def detect(self, *, current_tick: int) -> list[RuntimeWatchdogIncident]:
        incidents: list[RuntimeWatchdogIncident] = []
        for session in list(self._sessions.values()):
            if session.terminal:
                continue

            age = int(current_tick) - int(session.last_heartbeat_tick)
            if session.frozen or session.status == WATCHDOG_SESSION_STATUS_FROZEN:
                incidents.append(
                    self._create_incident(
                        incident_type=WATCHDOG_INCIDENT_TYPE_FROZEN,
                        session=session,
                        current_tick=current_tick,
                        reason="runtime session is frozen",
                    )
                )
                continue

            if age >= self.dead_after_ticks:
                incidents.append(
                    self._create_incident(
                        incident_type=WATCHDOG_INCIDENT_TYPE_DEAD,
                        session=session,
                        current_tick=current_tick,
                        reason="runtime session heartbeat exceeded dead threshold",
                    )
                )
                continue

            if age >= self.stall_after_ticks:
                incidents.append(
                    self._create_incident(
                        incident_type=WATCHDOG_INCIDENT_TYPE_STALLED,
                        session=session,
                        current_tick=current_tick,
                        reason="runtime session heartbeat exceeded stall threshold",
                    )
                )

        return incidents

    def tick(
        self,
        *,
        current_tick: int,
        submit_to_recovery: bool = True,
    ) -> dict[str, Any]:
        incidents = self.detect(current_tick=current_tick)
        submitted = []

        if submit_to_recovery and self.orchestrator is not None:
            for incident in incidents:
                try:
                    ticket = self.orchestrator.submit_incident(
                        incident.to_dict(),
                        current_tick=current_tick,
                    )
                    submitted.append(ticket.to_dict() if hasattr(ticket, "to_dict") else copy.deepcopy(ticket))
                except Exception as exc:
                    self._record_event(
                        "runtime_watchdog_recovery_submit_failed",
                        {
                            "incident": incident.to_dict(),
                            "error": {"type": type(exc).__name__, "message": str(exc)},
                        },
                    )

        return {
            "ok": True,
            "runtime_phase": "runtime_watchdog_tick",
            "current_tick": int(current_tick),
            "incident_count": len(incidents),
            "incidents": [incident.to_dict() for incident in incidents],
            "submitted_recovery_tickets": submitted,
        }

    def get_session(self, session_id: str) -> RuntimeWatchdogSession:
        session_id = self._validate_text("session_id", session_id)
        session = self._sessions.get(session_id)
        if session is None:
            raise RuntimeWatchdogRejected(f"runtime watchdog session does not exist: {session_id!r}")
        return copy.deepcopy(session)

    def list_sessions(self) -> list[RuntimeWatchdogSession]:
        return [copy.deepcopy(self._sessions[key]) for key in sorted(self._sessions)]

    def list_incidents(self) -> list[RuntimeWatchdogIncident]:
        return [
            copy.deepcopy(self._incidents[incident_id])
            for incident_id in self._incident_order
            if incident_id in self._incidents
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_phase": "runtime_watchdog",
            "stall_after_ticks": self.stall_after_ticks,
            "dead_after_ticks": self.dead_after_ticks,
            "sessions": [self._sessions[key].to_dict() for key in sorted(self._sessions)],
            "heartbeats": [heartbeat.to_dict() for heartbeat in self._heartbeats[-200:]],
            "incidents": [
                self._incidents[incident_id].to_dict()
                for incident_id in self._incident_order
                if incident_id in self._incidents
            ],
        }

    def load(self) -> None:
        if self.storage_path is None:
            return
        if not self.storage_path.exists():
            self._sessions = {}
            self._heartbeats = []
            self._incidents = {}
            self._incident_order = []
            return

        payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        self._sessions = {}
        self._heartbeats = []
        self._incidents = {}
        self._incident_order = []

        if isinstance(payload, dict):
            for item in payload.get("sessions") or []:
                if isinstance(item, dict):
                    session = RuntimeWatchdogSession.from_dict(item)
                    if session.session_id:
                        self._sessions[session.session_id] = session
            for item in payload.get("heartbeats") or []:
                if isinstance(item, dict):
                    heartbeat = RuntimeHeartbeat.from_dict(item)
                    if heartbeat.session_id:
                        self._heartbeats.append(heartbeat)
            for item in payload.get("incidents") or []:
                if isinstance(item, dict):
                    incident = RuntimeWatchdogIncident(
                        incident_id=str(item.get("incident_id") or ""),
                        incident_type=str(item.get("incident_type") or ""),
                        session_id=str(item.get("session_id") or item.get("source_session_id") or ""),
                        task_id=str(item.get("task_id") or ""),
                        current_tick=_safe_int(item.get("current_tick"), 0),
                        last_heartbeat_tick=_safe_int(item.get("last_heartbeat_tick"), 0),
                        status=str(item.get("status") or "open"),
                        source=str(item.get("source") or "runtime_watchdog"),
                        payload=_copy_dict(item.get("payload")),
                        metadata=_copy_dict(item.get("metadata")),
                        created_at=str(item.get("created_at") or utc_timestamp()),
                    )
                    if incident.incident_id:
                        self._incidents[incident.incident_id] = incident
                        self._incident_order.append(incident.incident_id)

    def save(self) -> None:
        if self.storage_path is None:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _create_incident(
        self,
        *,
        incident_type: str,
        session: RuntimeWatchdogSession,
        current_tick: int,
        reason: str,
    ) -> RuntimeWatchdogIncident:
        incident_id = "runtime-watchdog-incident-" + stable_watchdog_fingerprint(
            {
                "incident_type": incident_type,
                "session_id": session.session_id,
                "last_heartbeat_tick": session.last_heartbeat_tick,
            }
        )[:16]

        existing = self._incidents.get(incident_id)
        if existing is not None:
            return copy.deepcopy(existing)

        if incident_type == WATCHDOG_INCIDENT_TYPE_DEAD:
            status = WATCHDOG_SESSION_STATUS_DEAD
        elif incident_type == WATCHDOG_INCIDENT_TYPE_FROZEN:
            status = WATCHDOG_SESSION_STATUS_FROZEN
        else:
            status = WATCHDOG_SESSION_STATUS_STALLED

        updated_session = RuntimeWatchdogSession.from_dict(
            {
                **session.to_dict(),
                "status": status,
                "last_observed_tick": int(current_tick),
                "updated_at": utc_timestamp(),
            }
        )
        self._sessions[session.session_id] = updated_session

        incident = RuntimeWatchdogIncident(
            incident_id=incident_id,
            incident_type=incident_type,
            session_id=session.session_id,
            task_id=session.task_id,
            current_tick=int(current_tick),
            last_heartbeat_tick=session.last_heartbeat_tick,
            payload={"reason": reason, "session": updated_session.to_dict()},
            metadata={
                "stall_after_ticks": self.stall_after_ticks,
                "dead_after_ticks": self.dead_after_ticks,
            },
        )
        self._incidents[incident_id] = incident
        self._incident_order.append(incident_id)
        self.save()
        self._record_event(
            "runtime_watchdog_incident_created",
            {"incident": incident.to_dict()},
        )
        return copy.deepcopy(incident)

    def _record_event(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            "event_type": event_type,
            "payload": copy.deepcopy(payload),
            "timestamp": utc_timestamp(),
            "source": "runtime_watchdog",
        }

        for target in (self.audit, self.journal):
            if target is None:
                continue
            try:
                if hasattr(target, "append"):
                    target.append(event)
                elif hasattr(target, "record_event"):
                    target.record_event(event)
                elif hasattr(target, "record"):
                    target.record(event)
                elif hasattr(target, "append_record"):
                    target.append_record("runtime_watchdog", event)
            except Exception:
                pass

    def _validate_text(self, field_name: str, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise RuntimeWatchdogRejected(f"{field_name}_required")
        return text
