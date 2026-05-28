from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_supervisor_bridge_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeSupervisorBridgeResult:
    ok: bool
    bridge_id: str
    current_tick: int
    watchdog_lease_result: dict[str, Any] = field(default_factory=dict)
    supervisor_cases: list[dict[str, Any]] = field(default_factory=list)
    recovery_results: list[dict[str, Any]] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "bridge_id": self.bridge_id,
            "runtime_phase": "runtime_supervisor_bridge",
            "current_tick": self.current_tick,
            "watchdog_lease_result": copy.deepcopy(self.watchdog_lease_result),
            "supervisor_cases": copy.deepcopy(self.supervisor_cases),
            "recovery_results": copy.deepcopy(self.recovery_results),
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class RuntimeSupervisorBridgeEvent:
    event_id: str
    event_type: str
    bridge_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "bridge_id": self.bridge_id,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "timestamp": self.timestamp,
            "source": "runtime_supervisor_bridge",
        }


class RuntimeSupervisorBridgeRejected(RuntimeError):
    pass


class RuntimeSupervisorBridge:
    """
    Mainline bridge for the governed runtime fabric.

    Canonical flow:
        watchdog_lease_bridge.tick()
          -> incidents
          -> supervisor.process_many()
          -> recovery_orchestrator.consume_ready()

    This bridge does not own watchdog, lease, supervisor, or recovery internals.
    It only wires the lifecycle together and produces an auditable bridge result.
    """

    def __init__(
        self,
        *,
        watchdog_lease_bridge: Any,
        supervisor: Any,
        recovery_orchestrator: Any = None,
        storage_path: str | Path | None = None,
        journal: Any = None,
        audit: Any = None,
    ) -> None:
        if watchdog_lease_bridge is None:
            raise RuntimeSupervisorBridgeRejected("watchdog_lease_bridge_required")
        if supervisor is None:
            raise RuntimeSupervisorBridgeRejected("runtime_supervisor_required")

        self.watchdog_lease_bridge = watchdog_lease_bridge
        self.supervisor = supervisor
        self.recovery_orchestrator = recovery_orchestrator
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self.journal = journal
        self.audit = audit
        self._results: list[RuntimeSupervisorBridgeResult] = []
        self._events: list[RuntimeSupervisorBridgeEvent] = []
        if self.storage_path is not None:
            self.load()

    @classmethod
    def with_workspace(
        cls,
        workspace_root: str | Path = "workspace",
        **kwargs: Any,
    ) -> "RuntimeSupervisorBridge":
        root = Path(workspace_root)
        bridge_dir = root / "runtime_supervisor_bridge"
        bridge_dir.mkdir(parents=True, exist_ok=True)
        return cls(storage_path=bridge_dir / "runtime_supervisor_bridge.json", **kwargs)

    def tick(
        self,
        *,
        current_tick: int,
        submit_to_recovery_from_watchdog: bool = False,
        run_recovery_queue: bool = True,
        recovery_limit: int = 10,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeSupervisorBridgeResult:
        """
        Run one governed supervisor bridge cycle.

        submit_to_recovery_from_watchdog should normally remain False here.
        The supervisor is the authority that decides recover/takeover/freeze.
        """

        bridge_id = "runtime-supervisor-bridge-" + stable_supervisor_bridge_fingerprint(
            {
                "current_tick": current_tick,
                "sequence": len(self._results) + 1,
            }
        )[:16]

        watchdog_lease_result = self.watchdog_lease_bridge.tick(
            current_tick=current_tick,
            submit_to_recovery=submit_to_recovery_from_watchdog,
        )
        incidents = watchdog_lease_result.get("incidents", [])
        if not isinstance(incidents, list):
            incidents = []

        self._append_event(
            "runtime_supervisor_bridge_watchdog_lease_tick",
            bridge_id=bridge_id,
            payload={"watchdog_lease_result": copy.deepcopy(watchdog_lease_result)},
        )

        supervisor_cases = []
        if incidents:
            if hasattr(self.supervisor, "process_many"):
                cases = self.supervisor.process_many(
                    [item for item in incidents if isinstance(item, dict)],
                    current_tick=current_tick,
                )
            else:
                cases = [
                    self.supervisor.process_incident(item, current_tick=current_tick)
                    for item in incidents
                    if isinstance(item, dict)
                ]

            for case in cases:
                supervisor_cases.append(case.to_dict() if hasattr(case, "to_dict") else copy.deepcopy(case))

        self._append_event(
            "runtime_supervisor_bridge_supervisor_processed",
            bridge_id=bridge_id,
            payload={"supervisor_cases": copy.deepcopy(supervisor_cases)},
        )

        recovery_results = []
        orchestrator = self.recovery_orchestrator or getattr(self.supervisor, "orchestrator", None)
        if run_recovery_queue and orchestrator is not None and hasattr(orchestrator, "consume_ready"):
            queued_recovery = any(
                str(case.get("status") or "") == "recovery_queued"
                or bool(case.get("recovery_ticket"))
                for case in supervisor_cases
                if isinstance(case, dict)
            )
            if queued_recovery:
                consumed = orchestrator.consume_ready(
                    current_tick=current_tick,
                    limit=recovery_limit,
                )
                for item in consumed:
                    recovery_results.append(item.to_dict() if hasattr(item, "to_dict") else copy.deepcopy(item))

        self._append_event(
            "runtime_supervisor_bridge_recovery_consumed",
            bridge_id=bridge_id,
            payload={"recovery_results": copy.deepcopy(recovery_results)},
        )

        result = RuntimeSupervisorBridgeResult(
            ok=True,
            bridge_id=bridge_id,
            current_tick=int(current_tick),
            watchdog_lease_result=copy.deepcopy(watchdog_lease_result),
            supervisor_cases=copy.deepcopy(supervisor_cases),
            recovery_results=copy.deepcopy(recovery_results),
            metadata=copy.deepcopy(metadata or {}),
        )
        self._results.append(result)
        self.save()
        self._record_external_event(
            {
                "event_type": "runtime_supervisor_bridge_tick_completed",
                "payload": result.to_dict(),
                "timestamp": utc_timestamp(),
                "source": "runtime_supervisor_bridge",
            }
        )
        return copy.deepcopy(result)

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
        if not hasattr(self.watchdog_lease_bridge, "register_session"):
            raise RuntimeSupervisorBridgeRejected("watchdog_lease_bridge_register_session_unavailable")
        result = self.watchdog_lease_bridge.register_session(
            session_id,
            owner_id,
            task_id=task_id,
            current_tick=current_tick,
            acquire_lease=acquire_lease,
            ttl_ticks=ttl_ticks,
            payload=payload,
            metadata=metadata,
        )
        self._record_external_event(
            {
                "event_type": "runtime_supervisor_bridge_session_registered",
                "payload": copy.deepcopy(result),
                "timestamp": utc_timestamp(),
                "source": "runtime_supervisor_bridge",
            }
        )
        self.save()
        return copy.deepcopy(result)

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
        if not hasattr(self.watchdog_lease_bridge, "heartbeat"):
            raise RuntimeSupervisorBridgeRejected("watchdog_lease_bridge_heartbeat_unavailable")
        result = self.watchdog_lease_bridge.heartbeat(
            session_id,
            owner_id,
            task_id=task_id,
            current_tick=current_tick,
            watchdog_status=watchdog_status,
            payload=payload,
            metadata=metadata,
        )
        self._record_external_event(
            {
                "event_type": "runtime_supervisor_bridge_heartbeat",
                "payload": copy.deepcopy(result),
                "timestamp": utc_timestamp(),
                "source": "runtime_supervisor_bridge",
            }
        )
        self.save()
        return copy.deepcopy(result)

    def latest_result(self) -> RuntimeSupervisorBridgeResult | None:
        if not self._results:
            return None
        return copy.deepcopy(self._results[-1])

    def list_results(self) -> list[RuntimeSupervisorBridgeResult]:
        return [copy.deepcopy(item) for item in self._results]

    def list_events(self) -> list[RuntimeSupervisorBridgeEvent]:
        return [copy.deepcopy(item) for item in self._events]

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_phase": "runtime_supervisor_bridge",
            "results": [item.to_dict() for item in self._results[-300:]],
            "events": [item.to_dict() for item in self._events[-500:]],
        }

    def load(self) -> None:
        if self.storage_path is None:
            return
        if not self.storage_path.exists():
            self._results = []
            self._events = []
            return

        payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        self._results = []
        self._events = []
        if not isinstance(payload, dict):
            return

        for item in payload.get("results") or []:
            if not isinstance(item, dict):
                continue
            result = RuntimeSupervisorBridgeResult(
                ok=bool(item.get("ok", False)),
                bridge_id=str(item.get("bridge_id") or ""),
                current_tick=int(item.get("current_tick") or 0),
                watchdog_lease_result=copy.deepcopy(item.get("watchdog_lease_result") if isinstance(item.get("watchdog_lease_result"), dict) else {}),
                supervisor_cases=copy.deepcopy(item.get("supervisor_cases") if isinstance(item.get("supervisor_cases"), list) else []),
                recovery_results=copy.deepcopy(item.get("recovery_results") if isinstance(item.get("recovery_results"), list) else []),
                payload=copy.deepcopy(item.get("payload") if isinstance(item.get("payload"), dict) else {}),
                metadata=copy.deepcopy(item.get("metadata") if isinstance(item.get("metadata"), dict) else {}),
                timestamp=str(item.get("timestamp") or utc_timestamp()),
            )
            if result.bridge_id:
                self._results.append(result)

        for item in payload.get("events") or []:
            if not isinstance(item, dict):
                continue
            event = RuntimeSupervisorBridgeEvent(
                event_id=str(item.get("event_id") or ""),
                event_type=str(item.get("event_type") or ""),
                bridge_id=str(item.get("bridge_id") or ""),
                payload=copy.deepcopy(item.get("payload") if isinstance(item.get("payload"), dict) else {}),
                metadata=copy.deepcopy(item.get("metadata") if isinstance(item.get("metadata"), dict) else {}),
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

    def _append_event(
        self,
        event_type: str,
        *,
        bridge_id: str,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        event_id = "runtime-supervisor-bridge-event-" + stable_supervisor_bridge_fingerprint(
            {
                "event_type": event_type,
                "bridge_id": bridge_id,
                "sequence": len(self._events) + 1,
            }
        )[:16]
        event = RuntimeSupervisorBridgeEvent(
            event_id=event_id,
            event_type=event_type,
            bridge_id=bridge_id,
            payload=copy.deepcopy(payload or {}),
            metadata=copy.deepcopy(metadata or {}),
        )
        self._events.append(event)
        self._record_external_event(event.to_dict())

    def _record_external_event(self, event: dict[str, Any]) -> None:
        for target in (self.audit, self.journal):
            if target is None:
                continue
            try:
                if hasattr(target, "append"):
                    target.append(copy.deepcopy(event))
                elif hasattr(target, "record_event"):
                    target.record_event(copy.deepcopy(event))
                elif hasattr(target, "record"):
                    target.record(copy.deepcopy(event))
                elif hasattr(target, "append_record"):
                    target.append_record("runtime_supervisor_bridge", copy.deepcopy(event))
            except Exception:
                pass
