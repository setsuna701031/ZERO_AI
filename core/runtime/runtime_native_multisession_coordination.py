from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


RUNTIME_NODE_ACTIVE = "active"
RUNTIME_NODE_BLOCKED = "blocked"
RUNTIME_NODE_QUARANTINED = "quarantined"
RUNTIME_NODE_OFFLINE = "offline"

SIGNAL_STATUS_QUEUED = "queued"
SIGNAL_STATUS_DELIVERED = "delivered"
SIGNAL_STATUS_BLOCKED = "blocked"
SIGNAL_STATUS_FAILED = "failed"

SIGNAL_TYPE_MESSAGE = "message"
SIGNAL_TYPE_EXECUTION_REQUEST = "execution_request"
SIGNAL_TYPE_RECOVERY_REQUEST = "recovery_request"
SIGNAL_TYPE_RECOVERY_RESULT = "recovery_result"
SIGNAL_TYPE_RENDEZVOUS = "rendezvous"

RENDEZVOUS_STATUS_OPEN = "open"
RENDEZVOUS_STATUS_JOINED = "joined"
RENDEZVOUS_STATUS_COMPLETED = "completed"
RENDEZVOUS_STATUS_FAILED = "failed"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_coordination_fingerprint(value: Any) -> str:
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
class RuntimeFederationNode:
    node_id: str
    runtime_id: str
    namespace: str
    owner_id: str
    source_session_id: str = ""
    role: str = "runtime"
    status: str = RUNTIME_NODE_ACTIVE
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "runtime_id": self.runtime_id,
            "namespace": self.namespace,
            "owner_id": self.owner_id,
            "source_session_id": self.source_session_id,
            "role": self.role,
            "status": self.status,
            "capabilities": copy.deepcopy(self.capabilities),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeFederationNode":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            node_id=str(data.get("node_id") or ""),
            runtime_id=str(data.get("runtime_id") or ""),
            namespace=str(data.get("namespace") or ""),
            owner_id=str(data.get("owner_id") or ""),
            source_session_id=str(data.get("source_session_id") or ""),
            role=str(data.get("role") or "runtime"),
            status=str(data.get("status") or RUNTIME_NODE_ACTIVE),
            capabilities=_copy_list(data.get("capabilities")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeSignal:
    signal_id: str
    signal_type: str
    source_node_id: str
    target_node_id: str
    status: str = SIGNAL_STATUS_QUEUED
    payload: dict[str, Any] = field(default_factory=dict)
    authority_ref: dict[str, Any] = field(default_factory=dict)
    recovery_ref: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "signal_type": self.signal_type,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "status": self.status,
            "payload": copy.deepcopy(self.payload),
            "authority_ref": copy.deepcopy(self.authority_ref),
            "recovery_ref": copy.deepcopy(self.recovery_ref),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeSignal":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            signal_id=str(data.get("signal_id") or ""),
            signal_type=str(data.get("signal_type") or SIGNAL_TYPE_MESSAGE),
            source_node_id=str(data.get("source_node_id") or ""),
            target_node_id=str(data.get("target_node_id") or ""),
            status=str(data.get("status") or SIGNAL_STATUS_QUEUED),
            payload=_copy_dict(data.get("payload")),
            authority_ref=_copy_dict(data.get("authority_ref")),
            recovery_ref=_copy_dict(data.get("recovery_ref")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeRendezvous:
    rendezvous_id: str
    name: str
    required_node_ids: list[str] = field(default_factory=list)
    joined_node_ids: list[str] = field(default_factory=list)
    status: str = RENDEZVOUS_STATUS_OPEN
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rendezvous_id": self.rendezvous_id,
            "name": self.name,
            "required_node_ids": copy.deepcopy(self.required_node_ids),
            "joined_node_ids": copy.deepcopy(self.joined_node_ids),
            "status": self.status,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeRendezvous":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            rendezvous_id=str(data.get("rendezvous_id") or ""),
            name=str(data.get("name") or ""),
            required_node_ids=_copy_list(data.get("required_node_ids")),
            joined_node_ids=_copy_list(data.get("joined_node_ids")),
            status=str(data.get("status") or RENDEZVOUS_STATUS_OPEN),
            payload=_copy_dict(data.get("payload")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeCoordinationEvent:
    event_id: str
    event_type: str
    ref_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "ref_id": self.ref_id,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "timestamp": self.timestamp,
            "source": "runtime_native_multisession_coordination",
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeCoordinationEvent":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            event_id=str(data.get("event_id") or ""),
            event_type=str(data.get("event_type") or ""),
            ref_id=str(data.get("ref_id") or ""),
            payload=_copy_dict(data.get("payload")),
            metadata=_copy_dict(data.get("metadata")),
            timestamp=str(data.get("timestamp") or utc_timestamp()),
        )


class RuntimeNativeMultiSessionCoordinationRejected(RuntimeError):
    pass



def _normalize_recovery_ticket_ref(value: Any, *, source_session_id: str = "", task_id: str = "", incident_id: str = "") -> dict[str, Any]:
    payload = value.to_dict() if hasattr(value, "to_dict") else copy.deepcopy(value)

    ticket: dict[str, Any]
    if isinstance(payload, dict):
        if isinstance(payload.get("recovery_ticket"), dict):
            ticket = copy.deepcopy(payload["recovery_ticket"])
        elif isinstance(payload.get("ticket"), dict):
            ticket = copy.deepcopy(payload["ticket"])
        elif isinstance(payload.get("result"), dict) and isinstance(payload["result"].get("recovery_ticket"), dict):
            ticket = copy.deepcopy(payload["result"]["recovery_ticket"])
        elif isinstance(payload.get("result"), dict) and isinstance(payload["result"].get("ticket"), dict):
            ticket = copy.deepcopy(payload["result"]["ticket"])
        elif isinstance(payload.get("recovery_result"), dict) and isinstance(payload["recovery_result"].get("recovery_ticket"), dict):
            ticket = copy.deepcopy(payload["recovery_result"]["recovery_ticket"])
        elif isinstance(payload.get("recovery_result"), dict) and isinstance(payload["recovery_result"].get("ticket"), dict):
            ticket = copy.deepcopy(payload["recovery_result"]["ticket"])
        else:
            ticket = copy.deepcopy(payload)
    else:
        ticket = {"raw_ticket": copy.deepcopy(payload)}

    if source_session_id and not ticket.get("source_session_id"):
        ticket["source_session_id"] = source_session_id
    if task_id and not ticket.get("task_id"):
        ticket["task_id"] = task_id
    if incident_id and not ticket.get("incident_id"):
        ticket["incident_id"] = incident_id
    if not ticket.get("status"):
        ticket["status"] = "queued"

    return {"recovery_ticket": ticket}

class RuntimeNativeMultiSessionCoordination:
    """
    Runtime-native multi-session coordination fabric.

    Responsibilities:
      - runtime federation registry
      - runtime mailbox / signal bus
      - cross-session authority routing
      - cross-runtime recovery propagation
      - rendezvous coordination
      - persistent signal state
    """

    def __init__(
        self,
        *,
        storage_path: str | Path | None = None,
        mainline: Any = None,
        scheduler: Any = None,
        dispatch: Any = None,
        recovery_orchestrator: Any = None,
        ownership_fabric: Any = None,
        supervisor_bridge: Any = None,
        journal: Any = None,
        audit: Any = None,
    ) -> None:
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self.mainline = mainline
        self.scheduler = scheduler
        self.dispatch = dispatch
        self.recovery_orchestrator = recovery_orchestrator or getattr(mainline, "orchestrator", None)
        self.ownership_fabric = ownership_fabric or getattr(mainline, "ownership_fabric", None)
        self.supervisor_bridge = supervisor_bridge or getattr(mainline, "supervisor_bridge", None)
        self.journal = journal
        self.audit = audit
        self._nodes: dict[str, RuntimeFederationNode] = {}
        self._node_order: list[str] = []
        self._signals: dict[str, RuntimeSignal] = {}
        self._signal_order: list[str] = []
        self._rendezvous: dict[str, RuntimeRendezvous] = {}
        self._rendezvous_order: list[str] = []
        self._events: list[RuntimeCoordinationEvent] = []
        if self.storage_path is not None:
            self.load()

    @classmethod
    def with_workspace(cls, workspace_root: str | Path = "workspace", **kwargs: Any) -> "RuntimeNativeMultiSessionCoordination":
        root = Path(workspace_root)
        coord_dir = root / "runtime_native_multisession_coordination"
        coord_dir.mkdir(parents=True, exist_ok=True)
        return cls(storage_path=coord_dir / "runtime_native_multisession_coordination.json", **kwargs)

    def register_node(
        self,
        *,
        runtime_id: str,
        namespace: str,
        owner_id: str,
        source_session_id: str = "",
        role: str = "runtime",
        capabilities: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        node_id: str | None = None,
    ) -> RuntimeFederationNode:
        runtime_id = self._validate_text("runtime_id", runtime_id)
        namespace = self._validate_text("namespace", namespace)
        owner_id = self._validate_text("owner_id", owner_id)
        if node_id is None:
            node_id = "runtime-node-" + stable_coordination_fingerprint(
                {
                    "runtime_id": runtime_id,
                    "namespace": namespace,
                    "owner_id": owner_id,
                    "source_session_id": source_session_id,
                    "role": role,
                }
            )[:16]
        node_id = self._validate_text("node_id", node_id)
        if node_id in self._nodes:
            raise RuntimeNativeMultiSessionCoordinationRejected(f"runtime node already exists: {node_id!r}")

        node = RuntimeFederationNode(
            node_id=node_id,
            runtime_id=runtime_id,
            namespace=namespace,
            owner_id=owner_id,
            source_session_id=str(source_session_id or ""),
            role=str(role or "runtime"),
            capabilities=_copy_list(capabilities or []),
            metadata=_copy_dict(metadata),
        )
        self._nodes[node_id] = node
        self._node_order.append(node_id)
        self._append_event("runtime_federation_node_registered", ref_id=node_id, payload={"node": node.to_dict()})
        self.save()
        return copy.deepcopy(node)

    def send_signal(
        self,
        *,
        source_node_id: str,
        target_node_id: str,
        signal_type: str = SIGNAL_TYPE_MESSAGE,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        signal_id: str | None = None,
    ) -> RuntimeSignal:
        source = self.get_node(source_node_id)
        target = self.get_node(target_node_id)
        if signal_id is None:
            signal_id = "runtime-signal-" + stable_coordination_fingerprint(
                {
                    "source_node_id": source_node_id,
                    "target_node_id": target_node_id,
                    "signal_type": signal_type,
                    "payload": payload or {},
                    "sequence": len(self._signal_order) + 1,
                }
            )[:16]
        signal_id = self._validate_text("signal_id", signal_id)

        authority_ref = self._authorize_cross_runtime(source, target, signal_type, payload or {})
        status = SIGNAL_STATUS_QUEUED if authority_ref.get("decision") in {"allow", ""} else SIGNAL_STATUS_BLOCKED

        signal = RuntimeSignal(
            signal_id=signal_id,
            signal_type=str(signal_type or SIGNAL_TYPE_MESSAGE),
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            status=status,
            payload=_copy_dict(payload),
            authority_ref=authority_ref,
            metadata=_copy_dict(metadata),
        )
        self._signals[signal_id] = signal
        self._signal_order.append(signal_id)
        self._append_event("runtime_signal_queued", ref_id=signal_id, payload={"signal": signal.to_dict()})
        self.save()
        return copy.deepcopy(signal)

    def deliver_ready_signals(self, *, limit: int = 10) -> list[RuntimeSignal]:
        ready = [
            signal for signal in self._signals.values()
            if signal.status == SIGNAL_STATUS_QUEUED
        ][:max(1, int(limit))]
        delivered = []
        for signal in ready:
            delivered.append(self.deliver_signal(signal.signal_id))
        return delivered

    def deliver_signal(self, signal_id: str) -> RuntimeSignal:
        signal = self.get_signal(signal_id)
        if signal.status != SIGNAL_STATUS_QUEUED:
            return signal

        recovery_ref = {}
        if signal.signal_type == SIGNAL_TYPE_RECOVERY_REQUEST:
            self._ensure_recovery_orchestrator()
            recovery_ref = self._propagate_recovery(signal)

        updated = RuntimeSignal.from_dict(
            {
                **signal.to_dict(),
                "status": SIGNAL_STATUS_DELIVERED,
                "recovery_ref": recovery_ref,
                "updated_at": utc_timestamp(),
            }
        )
        self._signals[signal_id] = updated
        self._append_event("runtime_signal_delivered", ref_id=signal_id, payload={"signal": updated.to_dict()})
        self.save()
        return copy.deepcopy(updated)

    def open_rendezvous(
        self,
        *,
        name: str,
        required_node_ids: list[str],
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        rendezvous_id: str | None = None,
    ) -> RuntimeRendezvous:
        name = self._validate_text("name", name)
        required = [self._validate_text("required_node_id", item) for item in required_node_ids]
        for node_id in required:
            self.get_node(node_id)

        if rendezvous_id is None:
            rendezvous_id = "runtime-rendezvous-" + stable_coordination_fingerprint(
                {
                    "name": name,
                    "required_node_ids": required,
                    "sequence": len(self._rendezvous_order) + 1,
                }
            )[:16]

        rv = RuntimeRendezvous(
            rendezvous_id=rendezvous_id,
            name=name,
            required_node_ids=required,
            payload=_copy_dict(payload),
            metadata=_copy_dict(metadata),
        )
        self._rendezvous[rendezvous_id] = rv
        self._rendezvous_order.append(rendezvous_id)
        self._append_event("runtime_rendezvous_opened", ref_id=rendezvous_id, payload={"rendezvous": rv.to_dict()})
        self.save()
        return copy.deepcopy(rv)

    def join_rendezvous(self, rendezvous_id: str, node_id: str) -> RuntimeRendezvous:
        rv = self.get_rendezvous(rendezvous_id)
        node_id = self._validate_text("node_id", node_id)
        self.get_node(node_id)

        joined = list(rv.joined_node_ids)
        if node_id not in joined:
            joined.append(node_id)

        status = RENDEZVOUS_STATUS_COMPLETED if set(rv.required_node_ids).issubset(set(joined)) else RENDEZVOUS_STATUS_JOINED

        updated = RuntimeRendezvous.from_dict(
            {
                **rv.to_dict(),
                "joined_node_ids": joined,
                "status": status,
                "updated_at": utc_timestamp(),
            }
        )
        self._rendezvous[rendezvous_id] = updated
        self._append_event("runtime_rendezvous_joined", ref_id=rendezvous_id, payload={"rendezvous": updated.to_dict(), "node_id": node_id})
        self.save()
        return copy.deepcopy(updated)

    def dispatch_between_nodes(
        self,
        *,
        source_node_id: str,
        target_node_id: str,
        goal: str,
        planner_fn: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
        step_runner: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None,
        resume_runner: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None,
        current_tick: int = 2,
    ) -> dict[str, Any]:
        signal = self.send_signal(
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            signal_type=SIGNAL_TYPE_EXECUTION_REQUEST,
            payload={"goal": goal},
        )
        if signal.status == SIGNAL_STATUS_BLOCKED:
            return {"ok": False, "status": "blocked", "signal": signal.to_dict()}

        delivered = self.deliver_signal(signal.signal_id)
        target = self.get_node(target_node_id)

        if self.dispatch is not None and hasattr(self.dispatch, "dispatch_goal"):
            result = self.dispatch.dispatch_goal(
                goal=goal,
                source_session_id=target.source_session_id,
                runtime_id=target.runtime_id,
                owner_id=target.owner_id,
                planner_fn=planner_fn,
                step_runner=step_runner,
                resume_runner=resume_runner,
                current_tick=current_tick,
                metadata={"coordination_signal_id": signal.signal_id},
            )
            result_payload = result.to_dict() if hasattr(result, "to_dict") else copy.deepcopy(result)
            return {"ok": result_payload.get("status") == "completed", "status": result_payload.get("status"), "signal": delivered.to_dict(), "dispatch": result_payload}

        if self.mainline is not None and hasattr(self.mainline, "run_goal"):
            result = self.mainline.run_goal(
                goal,
                planner_fn=planner_fn,
                step_runner=step_runner,
                resume_runner=resume_runner,
                current_tick=current_tick,
                metadata={"coordination_signal_id": signal.signal_id},
            )
            result_payload = result.to_dict() if hasattr(result, "to_dict") else copy.deepcopy(result)
            return {"ok": result_payload.get("status") == "completed", "status": result_payload.get("status"), "signal": delivered.to_dict(), "mainline": result_payload}

        return {"ok": False, "status": "no_dispatch_target", "signal": delivered.to_dict()}

    def get_node(self, node_id: str) -> RuntimeFederationNode:
        node_id = self._validate_text("node_id", node_id)
        node = self._nodes.get(node_id)
        if node is None:
            raise RuntimeNativeMultiSessionCoordinationRejected(f"runtime node does not exist: {node_id!r}")
        return copy.deepcopy(node)

    def get_signal(self, signal_id: str) -> RuntimeSignal:
        signal_id = self._validate_text("signal_id", signal_id)
        signal = self._signals.get(signal_id)
        if signal is None:
            raise RuntimeNativeMultiSessionCoordinationRejected(f"runtime signal does not exist: {signal_id!r}")
        return copy.deepcopy(signal)

    def get_rendezvous(self, rendezvous_id: str) -> RuntimeRendezvous:
        rendezvous_id = self._validate_text("rendezvous_id", rendezvous_id)
        rv = self._rendezvous.get(rendezvous_id)
        if rv is None:
            raise RuntimeNativeMultiSessionCoordinationRejected(f"runtime rendezvous does not exist: {rendezvous_id!r}")
        return copy.deepcopy(rv)

    def list_nodes(self) -> list[RuntimeFederationNode]:
        return [copy.deepcopy(self._nodes[node_id]) for node_id in self._node_order if node_id in self._nodes]

    def list_signals(self) -> list[RuntimeSignal]:
        return [copy.deepcopy(self._signals[signal_id]) for signal_id in self._signal_order if signal_id in self._signals]

    def list_rendezvous(self) -> list[RuntimeRendezvous]:
        return [copy.deepcopy(self._rendezvous[rv_id]) for rv_id in self._rendezvous_order if rv_id in self._rendezvous]

    def list_events(self) -> list[RuntimeCoordinationEvent]:
        return [copy.deepcopy(event) for event in self._events]

    def health(self) -> dict[str, Any]:
        signal_counts: dict[str, int] = {}
        for signal in self._signals.values():
            signal_counts[signal.status] = signal_counts.get(signal.status, 0) + 1
        return {
            "ok": True,
            "runtime_phase": "runtime_native_multisession_coordination_health",
            "nodes": len(self._nodes),
            "signals": len(self._signals),
            "rendezvous": len(self._rendezvous),
            "signal_counts": signal_counts,
            "events": len(self._events),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_phase": "runtime_native_multisession_coordination",
            "nodes": [self._nodes[node_id].to_dict() for node_id in self._node_order if node_id in self._nodes],
            "signals": [self._signals[signal_id].to_dict() for signal_id in self._signal_order if signal_id in self._signals],
            "rendezvous": [self._rendezvous[rv_id].to_dict() for rv_id in self._rendezvous_order if rv_id in self._rendezvous],
            "events": [event.to_dict() for event in self._events[-500:]],
        }

    def load(self) -> None:
        if self.storage_path is None or not self.storage_path.exists():
            return
        payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        self._nodes = {}
        self._node_order = []
        self._signals = {}
        self._signal_order = []
        self._rendezvous = {}
        self._rendezvous_order = []
        self._events = []
        if not isinstance(payload, dict):
            return
        for item in payload.get("nodes") or []:
            if isinstance(item, dict):
                node = RuntimeFederationNode.from_dict(item)
                if node.node_id:
                    self._nodes[node.node_id] = node
                    self._node_order.append(node.node_id)
        for item in payload.get("signals") or []:
            if isinstance(item, dict):
                signal = RuntimeSignal.from_dict(item)
                if signal.signal_id:
                    self._signals[signal.signal_id] = signal
                    self._signal_order.append(signal.signal_id)
        for item in payload.get("rendezvous") or []:
            if isinstance(item, dict):
                rv = RuntimeRendezvous.from_dict(item)
                if rv.rendezvous_id:
                    self._rendezvous[rv.rendezvous_id] = rv
                    self._rendezvous_order.append(rv.rendezvous_id)
        for item in payload.get("events") or []:
            if isinstance(item, dict):
                event = RuntimeCoordinationEvent.from_dict(item)
                if event.event_id:
                    self._events.append(event)

    def save(self) -> None:
        if self.storage_path is None:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def _authorize_cross_runtime(self, source: RuntimeFederationNode, target: RuntimeFederationNode, signal_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        if target.status != RUNTIME_NODE_ACTIVE:
            return {"decision": "deny", "reason": f"target node status blocks signal: {target.status}"}
        if source.status != RUNTIME_NODE_ACTIVE:
            return {"decision": "deny", "reason": f"source node status blocks signal: {source.status}"}
        if self.ownership_fabric is not None and hasattr(self.ownership_fabric, "authorize"):
            try:
                decision = self.ownership_fabric.authorize(
                    runtime_id=target.runtime_id,
                    capability="execute" if signal_type in {SIGNAL_TYPE_EXECUTION_REQUEST, SIGNAL_TYPE_RECOVERY_REQUEST} else "read",
                    target=f"runtime-signal://{source.node_id}/{target.node_id}/{signal_type}",
                    owner_id=target.owner_id,
                )
                return decision.to_dict() if hasattr(decision, "to_dict") else copy.deepcopy(decision)
            except Exception:
                return {"decision": "allow", "reason": "ownership fabric unavailable for target runtime"}
        return {"decision": "allow", "reason": "no ownership fabric configured"}

    def _ensure_recovery_orchestrator(self) -> Any:
        if self.recovery_orchestrator is not None:
            return self.recovery_orchestrator

        if self.mainline is not None and hasattr(self.mainline, "boot"):
            try:
                self.mainline.boot()
            except Exception:
                pass

        if self.mainline is not None:
            self.recovery_orchestrator = getattr(self.mainline, "orchestrator", None)
            self.ownership_fabric = self.ownership_fabric or getattr(self.mainline, "ownership_fabric", None)
            self.supervisor_bridge = self.supervisor_bridge or getattr(self.mainline, "supervisor_bridge", None)

        return self.recovery_orchestrator

    def _propagate_recovery(self, signal: RuntimeSignal) -> dict[str, Any]:
        source = self.get_node(signal.source_node_id)
        target = self.get_node(signal.target_node_id)

        source_session_id = target.source_session_id or target.runtime_id
        task_id = str(signal.payload.get("task_id") or "")
        incident_id = "coordination-recovery-incident-" + stable_coordination_fingerprint(signal.to_dict())[:16]

        orchestrator = self._ensure_recovery_orchestrator()
        if orchestrator is None:
            return _normalize_recovery_ticket_ref(
                {},
                source_session_id=source_session_id,
                task_id=task_id,
                incident_id=incident_id,
            )

        incident = {
            "incident_id": incident_id,
            "incident_type": "cross_runtime_recovery_request",
            "source_session_id": source_session_id,
            "runtime_session_id": source_session_id,
            "task_id": task_id,
            "event_type": "failure",
            "payload": {
                "source_node": source.to_dict(),
                "target_node": target.to_dict(),
                "signal": signal.to_dict(),
            },
            "metadata": {"coordination_signal_id": signal.signal_id},
            "source": "runtime_native_multisession_coordination",
        }

        if hasattr(orchestrator, "submit_incident"):
            submitted = orchestrator.submit_incident(
                incident,
                current_tick=_safe_int(signal.payload.get("current_tick"), 0),
            )
            return _normalize_recovery_ticket_ref(
                submitted,
                source_session_id=source_session_id,
                task_id=task_id,
                incident_id=incident_id,
            )

        if hasattr(orchestrator, "queue") and hasattr(orchestrator.queue, "enqueue"):
            ticket = orchestrator.queue.enqueue(
                recovery_id=incident_id,
                source_session_id=source_session_id,
                incident_id=incident_id,
                task_id=task_id,
                current_tick=_safe_int(signal.payload.get("current_tick"), 0),
            )
            return _normalize_recovery_ticket_ref(
                ticket,
                source_session_id=source_session_id,
                task_id=task_id,
                incident_id=incident_id,
            )

        return _normalize_recovery_ticket_ref(
            {},
            source_session_id=source_session_id,
            task_id=task_id,
            incident_id=incident_id,
        )

    def _append_event(self, event_type: str, *, ref_id: str = "", payload: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None) -> None:
        event_id = "runtime-coordination-event-" + stable_coordination_fingerprint(
            {"event_type": event_type, "ref_id": ref_id, "sequence": len(self._events) + 1}
        )[:16]
        event = RuntimeCoordinationEvent(
            event_id=event_id,
            event_type=event_type,
            ref_id=str(ref_id or ""),
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
                    target.append_record("runtime_native_multisession_coordination", event.to_dict())
            except Exception:
                pass

    def _validate_text(self, field_name: str, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise RuntimeNativeMultiSessionCoordinationRejected(f"{field_name}_required")
        return text
