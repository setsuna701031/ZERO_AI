from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LEASE_STATUS_ACTIVE = "active"
LEASE_STATUS_EXPIRED = "expired"
LEASE_STATUS_RELEASED = "released"
LEASE_STATUS_TRANSFERRED = "transferred"
LEASE_STATUS_REVOKED = "revoked"

SESSION_STATUS_REGISTERED = "registered"
SESSION_STATUS_ACTIVE = "active"
SESSION_STATUS_EXPIRED = "expired"
SESSION_STATUS_ZOMBIE = "zombie"
SESSION_STATUS_TRANSFERRED = "transferred"
SESSION_STATUS_RELEASED = "released"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_session_lease_fingerprint(value: Any) -> str:
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
class RuntimeSessionRecord:
    session_id: str
    owner_id: str = ""
    task_id: str = ""
    status: str = SESSION_STATUS_REGISTERED
    lease_id: str = ""
    last_heartbeat_tick: int = 0
    created_tick: int = 0
    updated_tick: int = 0
    takeover_count: int = 0
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "owner_id": self.owner_id,
            "task_id": self.task_id,
            "status": self.status,
            "lease_id": self.lease_id,
            "last_heartbeat_tick": self.last_heartbeat_tick,
            "created_tick": self.created_tick,
            "updated_tick": self.updated_tick,
            "takeover_count": self.takeover_count,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeSessionRecord":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            session_id=str(data.get("session_id") or ""),
            owner_id=str(data.get("owner_id") or ""),
            task_id=str(data.get("task_id") or ""),
            status=str(data.get("status") or SESSION_STATUS_REGISTERED),
            lease_id=str(data.get("lease_id") or ""),
            last_heartbeat_tick=_safe_int(data.get("last_heartbeat_tick"), 0),
            created_tick=_safe_int(data.get("created_tick"), 0),
            updated_tick=_safe_int(data.get("updated_tick"), 0),
            takeover_count=_safe_int(data.get("takeover_count"), 0),
            payload=_copy_dict(data.get("payload")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeSessionLease:
    lease_id: str
    session_id: str
    owner_id: str
    status: str = LEASE_STATUS_ACTIVE
    acquired_tick: int = 0
    renewed_tick: int = 0
    expires_tick: int = 0
    generation: int = 1
    previous_owner_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    acquired_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "session_id": self.session_id,
            "owner_id": self.owner_id,
            "status": self.status,
            "acquired_tick": self.acquired_tick,
            "renewed_tick": self.renewed_tick,
            "expires_tick": self.expires_tick,
            "generation": self.generation,
            "previous_owner_id": self.previous_owner_id,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "acquired_at": self.acquired_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeSessionLease":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            lease_id=str(data.get("lease_id") or ""),
            session_id=str(data.get("session_id") or ""),
            owner_id=str(data.get("owner_id") or ""),
            status=str(data.get("status") or LEASE_STATUS_ACTIVE),
            acquired_tick=_safe_int(data.get("acquired_tick"), 0),
            renewed_tick=_safe_int(data.get("renewed_tick"), 0),
            expires_tick=_safe_int(data.get("expires_tick"), 0),
            generation=max(1, _safe_int(data.get("generation"), 1)),
            previous_owner_id=str(data.get("previous_owner_id") or ""),
            payload=_copy_dict(data.get("payload")),
            metadata=_copy_dict(data.get("metadata")),
            acquired_at=str(data.get("acquired_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeSessionLeaseEvent:
    event_id: str
    event_type: str
    session_id: str
    owner_id: str = ""
    lease_id: str = ""
    current_tick: int = 0
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "session_id": self.session_id,
            "owner_id": self.owner_id,
            "lease_id": self.lease_id,
            "current_tick": self.current_tick,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "timestamp": self.timestamp,
            "source": "runtime_session_lease_registry",
        }


class RuntimeSessionLeaseRejected(RuntimeError):
    pass


class RuntimeSessionLeaseRegistry:
    """
    Persistent session ownership and lease authority.

    Lease expiry and heartbeat liveness are intentionally separate:

    - lease expiry controls ownership authority
    - zombie detection controls runtime liveness

    A long lease can still become zombie if its heartbeat is stale.
    """

    def __init__(
        self,
        storage_path: str | Path | None = None,
        *,
        default_ttl_ticks: int = 5,
        zombie_after_ticks: int = 15,
        journal: Any = None,
        audit: Any = None,
    ) -> None:
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self.default_ttl_ticks = max(1, int(default_ttl_ticks))
        self.zombie_after_ticks = max(1, int(zombie_after_ticks))
        self.journal = journal
        self.audit = audit
        self._sessions: dict[str, RuntimeSessionRecord] = {}
        self._leases: dict[str, RuntimeSessionLease] = {}
        self._events: list[RuntimeSessionLeaseEvent] = []
        if self.storage_path is not None:
            self.load()

    @classmethod
    def with_workspace(
        cls,
        workspace_root: str | Path = "workspace",
        **kwargs: Any,
    ) -> "RuntimeSessionLeaseRegistry":
        root = Path(workspace_root)
        lease_dir = root / "runtime_session_lease"
        lease_dir.mkdir(parents=True, exist_ok=True)
        return cls(lease_dir / "runtime_session_lease.json", **kwargs)

    def register_session(
        self,
        session_id: str,
        *,
        task_id: str = "",
        owner_id: str = "",
        current_tick: int = 0,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeSessionRecord:
        session_id = self._validate_text("session_id", session_id)
        existing = self._sessions.get(session_id)
        if existing is not None:
            merged_metadata = copy.deepcopy(existing.metadata)
            if metadata:
                merged_metadata.update(copy.deepcopy(metadata))
            session = RuntimeSessionRecord.from_dict(
                {
                    **existing.to_dict(),
                    "task_id": task_id or existing.task_id,
                    "owner_id": owner_id or existing.owner_id,
                    "updated_tick": int(current_tick),
                    "payload": copy.deepcopy(payload or existing.payload),
                    "metadata": merged_metadata,
                    "updated_at": utc_timestamp(),
                }
            )
        else:
            session = RuntimeSessionRecord(
                session_id=session_id,
                task_id=str(task_id or ""),
                owner_id=str(owner_id or ""),
                status=SESSION_STATUS_REGISTERED,
                last_heartbeat_tick=int(current_tick),
                created_tick=int(current_tick),
                updated_tick=int(current_tick),
                payload=copy.deepcopy(payload or {}),
                metadata=copy.deepcopy(metadata or {}),
            )
        self._sessions[session_id] = session
        self._append_event("runtime_session_registered", session_id, owner_id=owner_id, current_tick=current_tick, payload={"session": session.to_dict()})
        self.save()
        return copy.deepcopy(session)

    def acquire_lease(
        self,
        session_id: str,
        owner_id: str,
        *,
        current_tick: int = 0,
        ttl_ticks: int | None = None,
        force: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeSessionLease:
        session_id = self._validate_text("session_id", session_id)
        owner_id = self._validate_text("owner_id", owner_id)
        ttl = max(1, int(ttl_ticks if ttl_ticks is not None else self.default_ttl_ticks))

        if session_id not in self._sessions:
            self.register_session(session_id, owner_id=owner_id, current_tick=current_tick)

        current_lease = self._active_lease_for_session(session_id, current_tick=current_tick)
        if current_lease is not None and current_lease.owner_id != owner_id and not force:
            raise RuntimeSessionLeaseRejected(
                "runtime_session_lease_conflict: "
                f"session={session_id!r} active_owner={current_lease.owner_id!r}"
            )

        generation = 1
        previous_owner_id = ""
        if current_lease is not None:
            generation = current_lease.generation + (0 if current_lease.owner_id == owner_id else 1)
            previous_owner_id = current_lease.owner_id
            if current_lease.owner_id != owner_id:
                self._leases[current_lease.lease_id] = RuntimeSessionLease.from_dict(
                    {
                        **current_lease.to_dict(),
                        "status": LEASE_STATUS_TRANSFERRED,
                        "updated_at": utc_timestamp(),
                    }
                )

        lease_id = "runtime-session-lease-" + stable_session_lease_fingerprint(
            {
                "session_id": session_id,
                "owner_id": owner_id,
                "generation": generation,
            }
        )[:16]

        lease = RuntimeSessionLease(
            lease_id=lease_id,
            session_id=session_id,
            owner_id=owner_id,
            acquired_tick=int(current_tick),
            renewed_tick=int(current_tick),
            expires_tick=int(current_tick) + ttl,
            generation=generation,
            previous_owner_id=previous_owner_id if previous_owner_id != owner_id else "",
            metadata=copy.deepcopy(metadata or {}),
        )
        self._leases[lease_id] = lease

        old_session = self._sessions[session_id]
        session = RuntimeSessionRecord.from_dict(
            {
                **old_session.to_dict(),
                "owner_id": owner_id,
                "status": SESSION_STATUS_ACTIVE,
                "lease_id": lease_id,
                "updated_tick": int(current_tick),
                "updated_at": utc_timestamp(),
            }
        )
        self._sessions[session_id] = session
        self._append_event("runtime_session_lease_acquired", session_id, owner_id=owner_id, lease_id=lease_id, current_tick=current_tick, payload={"lease": lease.to_dict()})
        self.save()
        return copy.deepcopy(lease)

    def renew_lease(
        self,
        lease_id: str,
        owner_id: str,
        *,
        current_tick: int = 0,
        ttl_ticks: int | None = None,
        heartbeat: bool = True,
    ) -> RuntimeSessionLease:
        lease_id = self._validate_text("lease_id", lease_id)
        owner_id = self._validate_text("owner_id", owner_id)
        lease = self._leases.get(lease_id)
        if lease is None:
            raise RuntimeSessionLeaseRejected(f"runtime_session_lease_not_found: {lease_id!r}")
        if lease.owner_id != owner_id:
            raise RuntimeSessionLeaseRejected("runtime_session_lease_owner_mismatch")
        if lease.status != LEASE_STATUS_ACTIVE:
            raise RuntimeSessionLeaseRejected(f"runtime_session_lease_not_active: {lease.status!r}")
        if int(current_tick) > int(lease.expires_tick):
            expired = RuntimeSessionLease.from_dict({**lease.to_dict(), "status": LEASE_STATUS_EXPIRED, "updated_at": utc_timestamp()})
            self._leases[lease_id] = expired
            self._mark_session_expired(lease.session_id, current_tick=current_tick)
            self.save()
            raise RuntimeSessionLeaseRejected("runtime_session_lease_expired")

        ttl = max(1, int(ttl_ticks if ttl_ticks is not None else self.default_ttl_ticks))
        renewed = RuntimeSessionLease.from_dict(
            {
                **lease.to_dict(),
                "renewed_tick": int(current_tick),
                "expires_tick": int(current_tick) + ttl,
                "updated_at": utc_timestamp(),
            }
        )
        self._leases[lease_id] = renewed

        session = self._sessions.get(lease.session_id)
        if session is not None:
            self._sessions[lease.session_id] = RuntimeSessionRecord.from_dict(
                {
                    **session.to_dict(),
                    "status": SESSION_STATUS_ACTIVE,
                    "owner_id": owner_id,
                    "lease_id": lease_id,
                    "last_heartbeat_tick": int(current_tick) if heartbeat else session.last_heartbeat_tick,
                    "updated_tick": int(current_tick),
                    "updated_at": utc_timestamp(),
                }
            )

        self._append_event("runtime_session_lease_renewed", lease.session_id, owner_id=owner_id, lease_id=lease_id, current_tick=current_tick, payload={"lease": renewed.to_dict()})
        self.save()
        return copy.deepcopy(renewed)

    def heartbeat(
        self,
        session_id: str,
        owner_id: str,
        *,
        current_tick: int = 0,
    ) -> RuntimeSessionRecord:
        session_id = self._validate_text("session_id", session_id)
        owner_id = self._validate_text("owner_id", owner_id)
        session = self._sessions.get(session_id)
        if session is None:
            raise RuntimeSessionLeaseRejected(f"runtime_session_not_found: {session_id!r}")
        lease = self._leases.get(session.lease_id)
        if lease is None or lease.owner_id != owner_id or lease.status != LEASE_STATUS_ACTIVE:
            raise RuntimeSessionLeaseRejected("runtime_session_heartbeat_without_active_lease")
        self.renew_lease(lease.lease_id, owner_id, current_tick=current_tick, heartbeat=True)
        updated = self._sessions[session_id]
        self._append_event("runtime_session_heartbeat", session_id, owner_id=owner_id, lease_id=lease.lease_id, current_tick=current_tick, payload={"session": updated.to_dict()})
        self.save()
        return copy.deepcopy(updated)

    def release_lease(
        self,
        lease_id: str,
        owner_id: str,
        *,
        current_tick: int = 0,
    ) -> RuntimeSessionLease:
        lease_id = self._validate_text("lease_id", lease_id)
        owner_id = self._validate_text("owner_id", owner_id)
        lease = self._leases.get(lease_id)
        if lease is None:
            raise RuntimeSessionLeaseRejected(f"runtime_session_lease_not_found: {lease_id!r}")
        if lease.owner_id != owner_id:
            raise RuntimeSessionLeaseRejected("runtime_session_lease_owner_mismatch")
        released = RuntimeSessionLease.from_dict({**lease.to_dict(), "status": LEASE_STATUS_RELEASED, "updated_at": utc_timestamp()})
        self._leases[lease_id] = released

        session = self._sessions.get(lease.session_id)
        if session is not None:
            self._sessions[lease.session_id] = RuntimeSessionRecord.from_dict(
                {
                    **session.to_dict(),
                    "status": SESSION_STATUS_RELEASED,
                    "updated_tick": int(current_tick),
                    "updated_at": utc_timestamp(),
                }
            )
        self._append_event("runtime_session_lease_released", lease.session_id, owner_id=owner_id, lease_id=lease_id, current_tick=current_tick, payload={"lease": released.to_dict()})
        self.save()
        return copy.deepcopy(released)

    def takeover_session(
        self,
        session_id: str,
        new_owner_id: str,
        *,
        current_tick: int = 0,
        reason: str = "",
        ttl_ticks: int | None = None,
    ) -> RuntimeSessionLease:
        session_id = self._validate_text("session_id", session_id)
        new_owner_id = self._validate_text("new_owner_id", new_owner_id)
        session = self._sessions.get(session_id)
        if session is None:
            self.register_session(session_id, current_tick=current_tick)
            session = self._sessions[session_id]

        old_takeover_count = session.takeover_count
        lease = self.acquire_lease(
            session_id,
            new_owner_id,
            current_tick=current_tick,
            ttl_ticks=ttl_ticks,
            force=True,
            metadata={"takeover_reason": reason},
        )

        updated_session = self._sessions[session_id]
        self._sessions[session_id] = RuntimeSessionRecord.from_dict(
            {
                **updated_session.to_dict(),
                "status": SESSION_STATUS_TRANSFERRED,
                "takeover_count": old_takeover_count + 1,
                "updated_tick": int(current_tick),
                "updated_at": utc_timestamp(),
            }
        )
        self._append_event("runtime_session_takeover", session_id, owner_id=new_owner_id, lease_id=lease.lease_id, current_tick=current_tick, payload={"reason": reason, "lease": lease.to_dict()})
        self.save()
        return copy.deepcopy(lease)

    def detect_expired(self, *, current_tick: int) -> list[RuntimeSessionRecord]:
        expired: list[RuntimeSessionRecord] = []
        for session_id, session in list(self._sessions.items()):
            if session.status in {SESSION_STATUS_RELEASED, SESSION_STATUS_ZOMBIE}:
                continue
            lease = self._leases.get(session.lease_id)
            if lease is None:
                continue
            if lease.status == LEASE_STATUS_ACTIVE and int(current_tick) > int(lease.expires_tick):
                self._leases[lease.lease_id] = RuntimeSessionLease.from_dict(
                    {**lease.to_dict(), "status": LEASE_STATUS_EXPIRED, "updated_at": utc_timestamp()}
                )
                expired_session = self._mark_session_expired(session_id, current_tick=current_tick)
                expired.append(expired_session)
        self.save()
        return expired

    def detect_zombies(self, *, current_tick: int) -> list[RuntimeSessionRecord]:
        zombies: list[RuntimeSessionRecord] = []
        for session_id, session in list(self._sessions.items()):
            if session.status in {SESSION_STATUS_RELEASED, SESSION_STATUS_ZOMBIE}:
                continue

            heartbeat_tick = int(session.last_heartbeat_tick)
            if heartbeat_tick <= 0:
                heartbeat_tick = int(session.created_tick)

            age = int(current_tick) - heartbeat_tick
            if age >= int(self.zombie_after_ticks):
                zombie = RuntimeSessionRecord.from_dict(
                    {
                        **session.to_dict(),
                        "status": SESSION_STATUS_ZOMBIE,
                        "updated_tick": int(current_tick),
                        "updated_at": utc_timestamp(),
                    }
                )
                self._sessions[session_id] = zombie
                self._append_event(
                    "runtime_session_zombie_detected",
                    session_id,
                    owner_id=session.owner_id,
                    lease_id=session.lease_id,
                    current_tick=current_tick,
                    payload={
                        "session": zombie.to_dict(),
                        "age": age,
                        "zombie_after_ticks": self.zombie_after_ticks,
                    },
                )
                zombies.append(copy.deepcopy(zombie))
        self.save()
        return zombies

    def tick(self, *, current_tick: int) -> dict[str, Any]:
        expired = self.detect_expired(current_tick=current_tick)
        zombies = self.detect_zombies(current_tick=current_tick)
        return {
            "ok": True,
            "runtime_phase": "runtime_session_lease_tick",
            "current_tick": int(current_tick),
            "expired_sessions": [session.to_dict() for session in expired],
            "zombie_sessions": [session.to_dict() for session in zombies],
        }

    def get_session(self, session_id: str) -> RuntimeSessionRecord:
        session_id = self._validate_text("session_id", session_id)
        session = self._sessions.get(session_id)
        if session is None:
            raise RuntimeSessionLeaseRejected(f"runtime_session_not_found: {session_id!r}")
        return copy.deepcopy(session)

    def get_lease(self, lease_id: str) -> RuntimeSessionLease:
        lease_id = self._validate_text("lease_id", lease_id)
        lease = self._leases.get(lease_id)
        if lease is None:
            raise RuntimeSessionLeaseRejected(f"runtime_session_lease_not_found: {lease_id!r}")
        return copy.deepcopy(lease)

    def list_sessions(self) -> list[RuntimeSessionRecord]:
        return [copy.deepcopy(self._sessions[key]) for key in sorted(self._sessions)]

    def list_leases(self) -> list[RuntimeSessionLease]:
        return [copy.deepcopy(self._leases[key]) for key in sorted(self._leases)]

    def list_events(self) -> list[RuntimeSessionLeaseEvent]:
        return [copy.deepcopy(event) for event in self._events]

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_phase": "runtime_session_lease_registry",
            "default_ttl_ticks": self.default_ttl_ticks,
            "zombie_after_ticks": self.zombie_after_ticks,
            "sessions": [self._sessions[key].to_dict() for key in sorted(self._sessions)],
            "leases": [self._leases[key].to_dict() for key in sorted(self._leases)],
            "events": [event.to_dict() for event in self._events[-300:]],
        }

    def load(self) -> None:
        if self.storage_path is None:
            return
        if not self.storage_path.exists():
            self._sessions = {}
            self._leases = {}
            self._events = []
            return
        payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        self._sessions = {}
        self._leases = {}
        self._events = []
        if not isinstance(payload, dict):
            return
        for item in payload.get("sessions") or []:
            if isinstance(item, dict):
                session = RuntimeSessionRecord.from_dict(item)
                if session.session_id:
                    self._sessions[session.session_id] = session
        for item in payload.get("leases") or []:
            if isinstance(item, dict):
                lease = RuntimeSessionLease.from_dict(item)
                if lease.lease_id:
                    self._leases[lease.lease_id] = lease
        for item in payload.get("events") or []:
            if isinstance(item, dict):
                event = RuntimeSessionLeaseEvent(
                    event_id=str(item.get("event_id") or ""),
                    event_type=str(item.get("event_type") or ""),
                    session_id=str(item.get("session_id") or ""),
                    owner_id=str(item.get("owner_id") or ""),
                    lease_id=str(item.get("lease_id") or ""),
                    current_tick=_safe_int(item.get("current_tick"), 0),
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

    def _active_lease_for_session(self, session_id: str, *, current_tick: int) -> RuntimeSessionLease | None:
        session = self._sessions.get(session_id)
        if session is None or not session.lease_id:
            return None
        lease = self._leases.get(session.lease_id)
        if lease is None or lease.status != LEASE_STATUS_ACTIVE:
            return None
        if int(current_tick) > int(lease.expires_tick):
            self._leases[lease.lease_id] = RuntimeSessionLease.from_dict(
                {**lease.to_dict(), "status": LEASE_STATUS_EXPIRED, "updated_at": utc_timestamp()}
            )
            self._mark_session_expired(session_id, current_tick=current_tick)
            return None
        return lease

    def _mark_session_expired(self, session_id: str, *, current_tick: int) -> RuntimeSessionRecord:
        session = self._sessions.get(session_id)
        if session is None:
            raise RuntimeSessionLeaseRejected(f"runtime_session_not_found: {session_id!r}")
        expired = RuntimeSessionRecord.from_dict(
            {
                **session.to_dict(),
                "status": SESSION_STATUS_EXPIRED,
                "updated_tick": int(current_tick),
                "updated_at": utc_timestamp(),
            }
        )
        self._sessions[session_id] = expired
        self._append_event("runtime_session_lease_expired", session_id, owner_id=session.owner_id, lease_id=session.lease_id, current_tick=current_tick, payload={"session": expired.to_dict()})
        return copy.deepcopy(expired)

    def _append_event(
        self,
        event_type: str,
        session_id: str,
        *,
        owner_id: str = "",
        lease_id: str = "",
        current_tick: int = 0,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        event_id = "runtime-session-lease-event-" + stable_session_lease_fingerprint(
            {
                "event_type": event_type,
                "session_id": session_id,
                "owner_id": owner_id,
                "lease_id": lease_id,
                "current_tick": current_tick,
                "sequence": len(self._events) + 1,
            }
        )[:16]
        event = RuntimeSessionLeaseEvent(
            event_id=event_id,
            event_type=event_type,
            session_id=session_id,
            owner_id=str(owner_id or ""),
            lease_id=str(lease_id or ""),
            current_tick=int(current_tick),
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
                    target.append_record("runtime_session_lease", event.to_dict())
            except Exception:
                pass

    def _validate_text(self, field_name: str, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise RuntimeSessionLeaseRejected(f"{field_name}_required")
        return text
