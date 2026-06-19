from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.goals.goal_lineage_contract import extract_runtime_identity
from core.runtime.runtime_session_lease import (
    SESSION_STATUS_ZOMBIE,
    RuntimeSessionLeaseRegistry,
)


BRIDGE_INCIDENT_TYPE_LEASE_EXPIRED = "runtime_session_lease_expired"
BRIDGE_INCIDENT_TYPE_SESSION_ZOMBIE = "runtime_session_zombie"
BRIDGE_INCIDENT_TYPE_OWNERSHIP_MISMATCH = "runtime_session_ownership_mismatch"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_watchdog_lease_bridge_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeWatchdogLeaseIncident:
    incident_id: str
    incident_type: str
    session_id: str
    task_id: str = ""
    runtime_session_id: str = ""
    source_session_id: str = ""
    owner_id: str = ""
    lease_id: str = ""
    current_tick: int = 0
    status: str = "open"
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        identity = extract_runtime_identity(
            {
                "session_id": self.session_id,
                "runtime_session_id": self.runtime_session_id,
                "source_session_id": self.source_session_id,
            },
            reject_conflicts=True,
        )
        return {
            "incident_id": self.incident_id,
            "incident_type": self.incident_type,
            "session_id": identity.get("session_id", ""),
            "source_session_id": identity.get("source_session_id", ""),
            "runtime_session_id": identity.get("runtime_session_id", ""),
            "task_id": self.task_id,
            "owner_id": self.owner_id,
            "lease_id": self.lease_id,
            "current_tick": self.current_tick,
            "status": self.status,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "event_type": "failure",
            "source": "runtime_watchdog_lease_bridge",
        }


class RuntimeWatchdogLeaseBridgeRejected(RuntimeError):
    pass


class RuntimeWatchdogLeaseBridge:
    """
    Integrates RuntimeWatchdog with RuntimeSessionLeaseRegistry.

    Responsibilities:
    - mirror watchdog heartbeats into lease heartbeats
    - detect lease expiry / zombie state from the lease authority
    - submit lease incidents into recovery orchestrator
    - optionally trigger supervisor takeover for zombie sessions

    This bridge is intentionally separate from runtime_watchdog.py so the
    watchdog remains a pure liveness detector and the lease registry remains a
    pure ownership authority.
    """

    def __init__(
        self,
        *,
        lease_registry: RuntimeSessionLeaseRegistry | None = None,
        watchdog: Any = None,
        orchestrator: Any = None,
        supervisor_owner_id: str = "runtime-supervisor",
        auto_takeover_zombies: bool = False,
        journal: Any = None,
        audit: Any = None,
    ) -> None:
        self.lease_registry = lease_registry if lease_registry is not None else RuntimeSessionLeaseRegistry()
        self.watchdog = watchdog
        self.orchestrator = orchestrator
        self.supervisor_owner_id = str(supervisor_owner_id or "runtime-supervisor")
        self.auto_takeover_zombies = bool(auto_takeover_zombies)
        self.journal = journal
        self.audit = audit
        self._incidents: dict[str, RuntimeWatchdogLeaseIncident] = {}
        self._incident_order: list[str] = []

    @classmethod
    def with_workspace(
        cls,
        workspace_root: str | Path = "workspace",
        **kwargs: Any,
    ) -> "RuntimeWatchdogLeaseBridge":
        root = Path(workspace_root)
        lease_registry = kwargs.pop("lease_registry", None)
        if lease_registry is None:
            lease_registry = RuntimeSessionLeaseRegistry.with_workspace(root)
        return cls(lease_registry=lease_registry, **kwargs)

    def register_session(
        self,
        session_id: str,
        owner_id: str,
        *,
        task_id: str = "",
        current_tick: int = 0,
        acquire_lease: bool = True,
        ttl_ticks: int | None = None,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = self.lease_registry.register_session(
            session_id,
            task_id=task_id,
            owner_id=owner_id,
            current_tick=current_tick,
            payload=payload,
            metadata=metadata,
        )

        lease = None
        if acquire_lease:
            lease = self.lease_registry.acquire_lease(
                session_id,
                owner_id,
                current_tick=current_tick,
                ttl_ticks=ttl_ticks,
                metadata=metadata,
            )

        if self.watchdog is not None and hasattr(self.watchdog, "register_session"):
            try:
                self.watchdog.register_session(
                    session_id,
                    task_id=task_id,
                    current_tick=current_tick,
                    payload=payload,
                    metadata={
                        **copy.deepcopy(metadata or {}),
                        "lease_owner_id": owner_id,
                        "lease_id": lease.lease_id if lease is not None else "",
                    },
                )
            except Exception:
                pass

        self._record_event(
            "runtime_watchdog_lease_session_registered",
            {
                "session": session.to_dict(),
                "lease": lease.to_dict() if lease is not None else None,
            },
        )
        return {
            "ok": True,
            "session": session.to_dict(),
            "lease": lease.to_dict() if lease is not None else None,
        }

    def heartbeat(
        self,
        session_id: str,
        owner_id: str,
        *,
        task_id: str = "",
        current_tick: int = 0,
        watchdog_status: str = "running",
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = self.lease_registry.heartbeat(
            session_id,
            owner_id,
            current_tick=current_tick,
        )

        watchdog_heartbeat = None
        if self.watchdog is not None and hasattr(self.watchdog, "heartbeat"):
            watchdog_heartbeat = self.watchdog.heartbeat(
                session_id,
                task_id=task_id or session.task_id,
                status=watchdog_status,
                current_tick=current_tick,
                payload=payload,
                metadata={
                    **copy.deepcopy(metadata or {}),
                    "lease_owner_id": owner_id,
                    "lease_id": session.lease_id,
                },
            )

        self._record_event(
            "runtime_watchdog_lease_heartbeat",
            {
                "session": session.to_dict(),
                "watchdog_heartbeat": watchdog_heartbeat.to_dict()
                if hasattr(watchdog_heartbeat, "to_dict")
                else copy.deepcopy(watchdog_heartbeat),
            },
        )
        return {
            "ok": True,
            "session": session.to_dict(),
            "watchdog_heartbeat": watchdog_heartbeat.to_dict()
            if hasattr(watchdog_heartbeat, "to_dict")
            else copy.deepcopy(watchdog_heartbeat),
        }

    def tick(
        self,
        *,
        current_tick: int,
        submit_to_recovery: bool = True,
        run_watchdog_tick: bool = True,
    ) -> dict[str, Any]:
        lease_tick = self.lease_registry.tick(current_tick=current_tick)

        watchdog_tick = None
        if run_watchdog_tick and self.watchdog is not None and hasattr(self.watchdog, "tick"):
            try:
                watchdog_tick = self.watchdog.tick(
                    current_tick=current_tick,
                    submit_to_recovery=submit_to_recovery,
                )
            except TypeError:
                watchdog_tick = self.watchdog.tick(current_tick=current_tick)

        incidents: list[RuntimeWatchdogLeaseIncident] = []
        for session in lease_tick.get("expired_sessions", []):
            if isinstance(session, dict):
                incidents.append(
                    self._create_incident(
                        incident_type=BRIDGE_INCIDENT_TYPE_LEASE_EXPIRED,
                        session=session,
                        current_tick=current_tick,
                        reason="runtime session lease expired",
                    )
                )

        for session in lease_tick.get("zombie_sessions", []):
            if not isinstance(session, dict):
                continue
            incident = self._create_incident(
                incident_type=BRIDGE_INCIDENT_TYPE_SESSION_ZOMBIE,
                session=session,
                current_tick=current_tick,
                reason="runtime session heartbeat is stale under lease authority",
            )
            incidents.append(incident)

            if self.auto_takeover_zombies:
                try:
                    takeover = self.lease_registry.takeover_session(
                        session["session_id"],
                        self.supervisor_owner_id,
                        current_tick=current_tick,
                        reason="auto takeover zombie runtime session",
                    )
                    self._record_event(
                        "runtime_watchdog_lease_zombie_takeover",
                        {
                            "incident": incident.to_dict(),
                            "takeover_lease": takeover.to_dict(),
                        },
                    )
                except Exception as exc:
                    self._record_event(
                        "runtime_watchdog_lease_zombie_takeover_failed",
                        {
                            "incident": incident.to_dict(),
                            "error": {"type": type(exc).__name__, "message": str(exc)},
                        },
                    )

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
                        "runtime_watchdog_lease_recovery_submit_failed",
                        {
                            "incident": incident.to_dict(),
                            "error": {"type": type(exc).__name__, "message": str(exc)},
                        },
                    )

        result = {
            "ok": True,
            "runtime_phase": "runtime_watchdog_lease_bridge_tick",
            "current_tick": int(current_tick),
            "lease_tick": copy.deepcopy(lease_tick),
            "watchdog_tick": copy.deepcopy(watchdog_tick),
            "incident_count": len(incidents),
            "incidents": [incident.to_dict() for incident in incidents],
            "submitted_recovery_tickets": submitted,
        }
        self._record_event("runtime_watchdog_lease_tick", result)
        return result

    def assert_owner(
        self,
        session_id: str,
        expected_owner_id: str,
        *,
        current_tick: int = 0,
        submit_to_recovery: bool = True,
    ) -> dict[str, Any]:
        session = self.lease_registry.get_session(session_id)
        expected_owner_id = str(expected_owner_id or "").strip()
        if not expected_owner_id:
            raise RuntimeWatchdogLeaseBridgeRejected("expected_owner_id_required")

        if session.owner_id == expected_owner_id:
            return {
                "ok": True,
                "match": True,
                "session": session.to_dict(),
                "incident": None,
            }

        incident = self._create_incident(
            incident_type=BRIDGE_INCIDENT_TYPE_OWNERSHIP_MISMATCH,
            session=session.to_dict(),
            current_tick=current_tick,
            reason="runtime session owner does not match expected owner",
            metadata={"expected_owner_id": expected_owner_id, "actual_owner_id": session.owner_id},
        )

        submitted = None
        if submit_to_recovery and self.orchestrator is not None:
            ticket = self.orchestrator.submit_incident(incident.to_dict(), current_tick=current_tick)
            submitted = ticket.to_dict() if hasattr(ticket, "to_dict") else copy.deepcopy(ticket)

        return {
            "ok": False,
            "match": False,
            "session": session.to_dict(),
            "incident": incident.to_dict(),
            "submitted_recovery_ticket": submitted,
        }

    def list_incidents(self) -> list[RuntimeWatchdogLeaseIncident]:
        return [
            copy.deepcopy(self._incidents[incident_id])
            for incident_id in self._incident_order
            if incident_id in self._incidents
        ]

    def _create_incident(
        self,
        *,
        incident_type: str,
        session: dict[str, Any],
        current_tick: int,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeWatchdogLeaseIncident:
        session_id = str(session.get("session_id") or "")
        if not session_id:
            raise RuntimeWatchdogLeaseBridgeRejected("session_id_required_for_lease_incident")

        incident_id = "runtime-watchdog-lease-incident-" + stable_watchdog_lease_bridge_fingerprint(
            {
                "incident_type": incident_type,
                "session_id": session_id,
                "owner_id": session.get("owner_id"),
                "lease_id": session.get("lease_id"),
                "current_tick": current_tick,
            }
        )[:16]

        existing = self._incidents.get(incident_id)
        if existing is not None:
            return copy.deepcopy(existing)

        runtime_identity = extract_runtime_identity(session, reject_conflicts=True)
        incident = RuntimeWatchdogLeaseIncident(
            incident_id=incident_id,
            incident_type=incident_type,
            session_id=session_id,
            task_id=str(session.get("task_id") or ""),
            runtime_session_id=runtime_identity.get("runtime_session_id", ""),
            source_session_id=runtime_identity.get("source_session_id", ""),
            owner_id=str(session.get("owner_id") or ""),
            lease_id=str(session.get("lease_id") or ""),
            current_tick=int(current_tick),
            payload={"reason": reason, "session": copy.deepcopy(session)},
            metadata=copy.deepcopy(metadata or {}),
        )
        self._incidents[incident_id] = incident
        self._incident_order.append(incident_id)
        self._record_event(
            "runtime_watchdog_lease_incident_created",
            {"incident": incident.to_dict()},
        )
        return copy.deepcopy(incident)

    def _record_event(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            "event_type": event_type,
            "payload": copy.deepcopy(payload),
            "timestamp": utc_timestamp(),
            "source": "runtime_watchdog_lease_bridge",
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
                    target.append_record("runtime_watchdog_lease_bridge", event)
            except Exception:
                pass
