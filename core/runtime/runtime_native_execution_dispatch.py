from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


DISPATCH_STATUS_CREATED = "created"
DISPATCH_STATUS_ROUTED = "routed"
DISPATCH_STATUS_RUNNING = "running"
DISPATCH_STATUS_COMPLETED = "completed"
DISPATCH_STATUS_FAILED = "failed"
DISPATCH_STATUS_BLOCKED = "blocked"
DISPATCH_STATUS_RECOVERED = "recovered"
DISPATCH_STATUS_CONTINUATION_READY = "continuation_ready"

DISPATCH_NODE_ENTRY = "entry"
DISPATCH_NODE_EXECUTION = "execution"
DISPATCH_NODE_RECOVERY = "recovery"
DISPATCH_NODE_CONTINUATION = "continuation"
DISPATCH_NODE_COMPLETION = "completion"
DISPATCH_NODE_BLOCKED = "blocked"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_dispatch_fingerprint(value: Any) -> str:
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
class RuntimeDispatchNode:
    node_id: str
    dispatch_id: str
    node_type: str
    status: str = DISPATCH_STATUS_CREATED
    ref_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "dispatch_id": self.dispatch_id,
            "node_type": self.node_type,
            "status": self.status,
            "ref_id": self.ref_id,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeDispatchNode":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            node_id=str(data.get("node_id") or ""),
            dispatch_id=str(data.get("dispatch_id") or ""),
            node_type=str(data.get("node_type") or ""),
            status=str(data.get("status") or DISPATCH_STATUS_CREATED),
            ref_id=str(data.get("ref_id") or ""),
            payload=_copy_dict(data.get("payload")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeDispatchEdge:
    edge_id: str
    dispatch_id: str
    from_node_id: str
    to_node_id: str
    edge_type: str = "next"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "dispatch_id": self.dispatch_id,
            "from_node_id": self.from_node_id,
            "to_node_id": self.to_node_id,
            "edge_type": self.edge_type,
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeDispatchEdge":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            edge_id=str(data.get("edge_id") or ""),
            dispatch_id=str(data.get("dispatch_id") or ""),
            from_node_id=str(data.get("from_node_id") or ""),
            to_node_id=str(data.get("to_node_id") or ""),
            edge_type=str(data.get("edge_type") or "next"),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeDispatchRecord:
    dispatch_id: str
    goal: str
    source_session_id: str
    runtime_id: str = ""
    owner_id: str = ""
    schedule_id: str = ""
    task_id: str = ""
    execution_id: str = ""
    status: str = DISPATCH_STATUS_CREATED
    nodes: list[RuntimeDispatchNode] = field(default_factory=list)
    edges: list[RuntimeDispatchEdge] = field(default_factory=list)
    mainline_result: dict[str, Any] = field(default_factory=dict)
    scheduler_item: dict[str, Any] = field(default_factory=dict)
    recovery_ref: dict[str, Any] = field(default_factory=dict)
    continuation_ref: dict[str, Any] = field(default_factory=dict)
    authority_ref: dict[str, Any] = field(default_factory=dict)
    final_result: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dispatch_id": self.dispatch_id,
            "goal": self.goal,
            "source_session_id": self.source_session_id,
            "runtime_id": self.runtime_id,
            "owner_id": self.owner_id,
            "schedule_id": self.schedule_id,
            "task_id": self.task_id,
            "execution_id": self.execution_id,
            "status": self.status,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "mainline_result": copy.deepcopy(self.mainline_result),
            "scheduler_item": copy.deepcopy(self.scheduler_item),
            "recovery_ref": copy.deepcopy(self.recovery_ref),
            "continuation_ref": copy.deepcopy(self.continuation_ref),
            "authority_ref": copy.deepcopy(self.authority_ref),
            "final_result": copy.deepcopy(self.final_result),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeDispatchRecord":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            dispatch_id=str(data.get("dispatch_id") or ""),
            goal=str(data.get("goal") or ""),
            source_session_id=str(data.get("source_session_id") or ""),
            runtime_id=str(data.get("runtime_id") or ""),
            owner_id=str(data.get("owner_id") or ""),
            schedule_id=str(data.get("schedule_id") or ""),
            task_id=str(data.get("task_id") or ""),
            execution_id=str(data.get("execution_id") or ""),
            status=str(data.get("status") or DISPATCH_STATUS_CREATED),
            nodes=[RuntimeDispatchNode.from_dict(x) for x in data.get("nodes") or [] if isinstance(x, dict)],
            edges=[RuntimeDispatchEdge.from_dict(x) for x in data.get("edges") or [] if isinstance(x, dict)],
            mainline_result=_copy_dict(data.get("mainline_result")),
            scheduler_item=_copy_dict(data.get("scheduler_item")),
            recovery_ref=_copy_dict(data.get("recovery_ref")),
            continuation_ref=_copy_dict(data.get("continuation_ref")),
            authority_ref=_copy_dict(data.get("authority_ref")),
            final_result=_copy_dict(data.get("final_result")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeDispatchEvent:
    event_id: str
    event_type: str
    dispatch_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "dispatch_id": self.dispatch_id,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "timestamp": self.timestamp,
            "source": "runtime_native_execution_dispatch",
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeDispatchEvent":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            event_id=str(data.get("event_id") or ""),
            event_type=str(data.get("event_type") or ""),
            dispatch_id=str(data.get("dispatch_id") or ""),
            payload=_copy_dict(data.get("payload")),
            metadata=_copy_dict(data.get("metadata")),
            timestamp=str(data.get("timestamp") or utc_timestamp()),
        )


class RuntimeNativeExecutionDispatchRejected(RuntimeError):
    pass


PlannerFn = Callable[[str, dict[str, Any]], dict[str, Any]]
StepRunnerFn = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


class RuntimeNativeExecutionDispatch:
    """
    Runtime-native execution dispatch migration adapter.

    Bridges:
        scheduler -> dispatch graph -> runtime-native mainline -> execution fabric
    """

    def __init__(
        self,
        *,
        storage_path: str | Path | None = None,
        mainline: Any,
        scheduler: Any = None,
        ownership_fabric: Any = None,
        supervisor_bridge: Any = None,
        journal: Any = None,
        audit: Any = None,
    ) -> None:
        if mainline is None:
            raise RuntimeNativeExecutionDispatchRejected("runtime_native_mainline_required")
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self.mainline = mainline
        self.scheduler = scheduler
        self.ownership_fabric = ownership_fabric or getattr(mainline, "ownership_fabric", None)
        self.supervisor_bridge = supervisor_bridge or getattr(mainline, "supervisor_bridge", None)
        self.journal = journal
        self.audit = audit
        self._dispatches: dict[str, RuntimeDispatchRecord] = {}
        self._order: list[str] = []
        self._events: list[RuntimeDispatchEvent] = []
        if self.storage_path is not None:
            self.load()

    @classmethod
    def with_workspace(cls, workspace_root: str | Path = "workspace", **kwargs: Any) -> "RuntimeNativeExecutionDispatch":
        root = Path(workspace_root)
        dispatch_dir = root / "runtime_native_execution_dispatch"
        dispatch_dir.mkdir(parents=True, exist_ok=True)
        return cls(storage_path=dispatch_dir / "runtime_native_execution_dispatch.json", **kwargs)

    def create_dispatch(
        self,
        *,
        goal: str,
        source_session_id: str = "",
        runtime_id: str = "",
        owner_id: str = "",
        task_id: str = "",
        schedule_id: str = "",
        metadata: dict[str, Any] | None = None,
        dispatch_id: str | None = None,
    ) -> RuntimeDispatchRecord:
        goal = self._validate_text("goal", goal)
        config = getattr(self.mainline, "config", None)
        source_session_id = str(source_session_id or getattr(config, "source_session_id", "") or "")
        runtime_id = str(runtime_id or getattr(config, "runtime_id", "") or "")
        owner_id = str(owner_id or getattr(config, "owner_id", "") or "")

        if dispatch_id is None:
            dispatch_id = "runtime-dispatch-" + stable_dispatch_fingerprint(
                {
                    "goal": goal,
                    "source_session_id": source_session_id,
                    "runtime_id": runtime_id,
                    "task_id": task_id,
                    "schedule_id": schedule_id,
                    "sequence": len(self._order) + 1,
                }
            )[:16]
        dispatch_id = self._validate_text("dispatch_id", dispatch_id)

        if dispatch_id in self._dispatches:
            raise RuntimeNativeExecutionDispatchRejected(f"dispatch already exists: {dispatch_id!r}")

        entry = self._make_node(
            dispatch_id=dispatch_id,
            node_type=DISPATCH_NODE_ENTRY,
            status=DISPATCH_STATUS_CREATED,
            ref_id=source_session_id,
            payload={"goal": goal, "task_id": task_id, "schedule_id": schedule_id},
        )

        record = RuntimeDispatchRecord(
            dispatch_id=dispatch_id,
            goal=goal,
            source_session_id=source_session_id,
            runtime_id=runtime_id,
            owner_id=owner_id,
            task_id=str(task_id or ""),
            schedule_id=str(schedule_id or ""),
            nodes=[entry],
            metadata=copy.deepcopy(metadata or {}),
        )
        self._dispatches[dispatch_id] = record
        self._order.append(dispatch_id)
        self._append_event("runtime_dispatch_created", dispatch_id=dispatch_id, payload={"dispatch": record.to_dict()})
        self.save()
        return copy.deepcopy(record)

    def dispatch_goal(
        self,
        *,
        goal: str,
        source_session_id: str = "",
        runtime_id: str = "",
        owner_id: str = "",
        task_id: str = "",
        planner_fn: PlannerFn | None = None,
        step_runner: StepRunnerFn | None = None,
        resume_runner: StepRunnerFn | None = None,
        current_tick: int = 2,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeDispatchRecord:
        record = self.create_dispatch(
            goal=goal,
            source_session_id=source_session_id,
            runtime_id=runtime_id,
            owner_id=owner_id,
            task_id=task_id,
            metadata=metadata,
        )
        return self.run_dispatch(
            record.dispatch_id,
            planner_fn=planner_fn,
            step_runner=step_runner,
            resume_runner=resume_runner,
            current_tick=current_tick,
        )

    def dispatch_schedule_item(
        self,
        schedule_item: Any,
        *,
        planner_fn: PlannerFn | None = None,
        step_runner: StepRunnerFn | None = None,
        resume_runner: StepRunnerFn | None = None,
        current_tick: int = 2,
    ) -> RuntimeDispatchRecord:
        item = schedule_item.to_dict() if hasattr(schedule_item, "to_dict") else copy.deepcopy(schedule_item)
        if not isinstance(item, dict):
            raise RuntimeNativeExecutionDispatchRejected("schedule_item_must_be_dict")

        record = self.create_dispatch(
            goal=str(item.get("goal") or ""),
            source_session_id=str(item.get("source_session_id") or ""),
            runtime_id=str(item.get("runtime_id") or ""),
            owner_id=str(item.get("owner_id") or ""),
            task_id=str(item.get("task_id") or ""),
            schedule_id=str(item.get("schedule_id") or ""),
            metadata={"schedule_item": copy.deepcopy(item)},
        )
        return self.run_dispatch(
            record.dispatch_id,
            planner_fn=planner_fn,
            step_runner=step_runner,
            resume_runner=resume_runner,
            current_tick=current_tick,
        )

    def run_dispatch(
        self,
        dispatch_id: str,
        *,
        planner_fn: PlannerFn | None = None,
        step_runner: StepRunnerFn | None = None,
        resume_runner: StepRunnerFn | None = None,
        current_tick: int = 2,
    ) -> RuntimeDispatchRecord:
        record = self.get_dispatch(dispatch_id)
        routed = self._append_graph_node(
            record,
            node_type=DISPATCH_NODE_EXECUTION,
            status=DISPATCH_STATUS_ROUTED,
            ref_id=record.task_id or dispatch_id,
            payload={"runtime_id": record.runtime_id, "owner_id": record.owner_id},
            edge_type="route",
        )
        self._dispatches[dispatch_id] = routed

        try:
            result = self.mainline.run_goal(
                routed.goal,
                planner_fn=planner_fn,
                step_runner=step_runner,
                resume_runner=resume_runner,
                current_tick=current_tick,
                task_id=routed.task_id,
                metadata={
                    **copy.deepcopy(routed.metadata),
                    "dispatch_id": dispatch_id,
                    "dispatch_runtime_id": routed.runtime_id,
                    "dispatch_owner_id": routed.owner_id,
                    "dispatch_schedule_id": routed.schedule_id,
                },
            )
            result_payload = result.to_dict() if hasattr(result, "to_dict") else copy.deepcopy(result)
        except Exception as exc:
            result_payload = {
                "status": DISPATCH_STATUS_FAILED,
                "final_result": {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}},
            }

        status = str(result_payload.get("status") or "")
        if status == "completed":
            final_status = DISPATCH_STATUS_COMPLETED
        elif status == "blocked":
            final_status = DISPATCH_STATUS_BLOCKED
        else:
            final_status = DISPATCH_STATUS_FAILED

        loop_record = _copy_dict(result_payload.get("loop_record"))
        task_record = _copy_dict(loop_record.get("task"))
        recovery_ref = _copy_dict(task_record.get("recovery_ref"))
        continuation_ref = _copy_dict(task_record.get("continuation_ref"))

        recovery_ticket = _copy_dict(recovery_ref.get("recovery_ticket"))
        ticket_id = str(recovery_ticket.get("ticket_id") or "")
        if ticket_id:
            try:
                latest_ticket = self.mainline.orchestrator.queue.get_ticket(ticket_id)
                if hasattr(latest_ticket, "to_dict"):
                    recovery_ref["recovery_ticket"] = latest_ticket.to_dict()
            except Exception:
                pass

        node_type = DISPATCH_NODE_COMPLETION
        if final_status == DISPATCH_STATUS_BLOCKED:
            node_type = DISPATCH_NODE_BLOCKED
        elif recovery_ref:
            node_type = DISPATCH_NODE_RECOVERY

        updated = self._append_graph_node(
            self._replace_dispatch(
                routed,
                status=final_status,
                execution_id=str(result_payload.get("execution_id") or task_record.get("execution_id") or ""),
                mainline_result=result_payload,
                recovery_ref=recovery_ref,
                continuation_ref=continuation_ref,
                authority_ref=_copy_dict(result_payload.get("authority_decision")),
                final_result=_copy_dict(result_payload.get("final_result")),
            ),
            node_type=node_type,
            status=final_status,
            ref_id=str(result_payload.get("execution_id") or task_record.get("execution_id") or ""),
            payload={"mainline_result": result_payload, "recovery_ref": recovery_ref},
            edge_type="result",
        )

        if continuation_ref:
            updated = self._append_graph_node(
                updated,
                node_type=DISPATCH_NODE_CONTINUATION,
                status=DISPATCH_STATUS_CONTINUATION_READY,
                ref_id=str(continuation_ref.get("continuation_id") or ""),
                payload={"continuation_ref": continuation_ref},
                edge_type="continuation",
            )
            updated = RuntimeDispatchRecord.from_dict(
                {
                    **updated.to_dict(),
                    "status": final_status,
                    "updated_at": utc_timestamp(),
                }
            )

        self._dispatches[dispatch_id] = updated
        self._append_event("runtime_dispatch_completed", dispatch_id=dispatch_id, payload={"dispatch": updated.to_dict()})
        self.save()
        return copy.deepcopy(updated)

    def get_dispatch(self, dispatch_id: str) -> RuntimeDispatchRecord:
        dispatch_id = self._validate_text("dispatch_id", dispatch_id)
        record = self._dispatches.get(dispatch_id)
        if record is None:
            raise RuntimeNativeExecutionDispatchRejected(f"dispatch does not exist: {dispatch_id!r}")
        return copy.deepcopy(record)

    def list_dispatches(self) -> list[RuntimeDispatchRecord]:
        return [copy.deepcopy(self._dispatches[item_id]) for item_id in self._order if item_id in self._dispatches]

    def execution_map(self) -> dict[str, dict[str, Any]]:
        mapped: dict[str, dict[str, Any]] = {}
        for dispatch in self.list_dispatches():
            if dispatch.execution_id:
                mapped[dispatch.execution_id] = {
                    "dispatch_id": dispatch.dispatch_id,
                    "task_id": dispatch.task_id,
                    "schedule_id": dispatch.schedule_id,
                    "status": dispatch.status,
                    "runtime_id": dispatch.runtime_id,
                    "owner_id": dispatch.owner_id,
                    "source_session_id": dispatch.source_session_id,
                }
        return mapped

    def list_events(self) -> list[RuntimeDispatchEvent]:
        return [copy.deepcopy(event) for event in self._events]

    def health(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for dispatch in self._dispatches.values():
            counts[dispatch.status] = counts.get(dispatch.status, 0) + 1
        return {
            "ok": True,
            "runtime_phase": "runtime_native_execution_dispatch_health",
            "dispatches": len(self._dispatches),
            "counts": counts,
            "events": len(self._events),
            "execution_map_size": len(self.execution_map()),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_phase": "runtime_native_execution_dispatch",
            "dispatches": [self._dispatches[item_id].to_dict() for item_id in self._order if item_id in self._dispatches],
            "events": [event.to_dict() for event in self._events[-500:]],
        }

    def load(self) -> None:
        if self.storage_path is None or not self.storage_path.exists():
            return
        payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        self._dispatches = {}
        self._order = []
        self._events = []
        if not isinstance(payload, dict):
            return
        for item in payload.get("dispatches") or []:
            if isinstance(item, dict):
                dispatch = RuntimeDispatchRecord.from_dict(item)
                if dispatch.dispatch_id:
                    self._dispatches[dispatch.dispatch_id] = dispatch
                    self._order.append(dispatch.dispatch_id)
        for item in payload.get("events") or []:
            if isinstance(item, dict):
                event = RuntimeDispatchEvent.from_dict(item)
                if event.event_id:
                    self._events.append(event)

    def save(self) -> None:
        if self.storage_path is None:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def _make_node(
        self,
        *,
        dispatch_id: str,
        node_type: str,
        status: str,
        ref_id: str = "",
        payload: dict[str, Any] | None = None,
    ) -> RuntimeDispatchNode:
        existing = self._dispatches.get(dispatch_id)
        sequence = len(existing.nodes) + 1 if existing is not None else 1
        return RuntimeDispatchNode(
            node_id="runtime-dispatch-node-" + stable_dispatch_fingerprint(
                {
                    "dispatch_id": dispatch_id,
                    "node_type": node_type,
                    "status": status,
                    "ref_id": ref_id,
                    "payload": payload or {},
                    "sequence": sequence,
                }
            )[:16],
            dispatch_id=dispatch_id,
            node_type=node_type,
            status=status,
            ref_id=str(ref_id or ""),
            payload=copy.deepcopy(payload or {}),
        )

    def _append_graph_node(
        self,
        record: RuntimeDispatchRecord,
        *,
        node_type: str,
        status: str,
        ref_id: str = "",
        payload: dict[str, Any] | None = None,
        edge_type: str = "next",
    ) -> RuntimeDispatchRecord:
        node = self._make_node(
            dispatch_id=record.dispatch_id,
            node_type=node_type,
            status=status,
            ref_id=ref_id,
            payload=payload,
        )
        edges = [edge.to_dict() for edge in record.edges]
        if record.nodes:
            previous = record.nodes[-1]
            edge = RuntimeDispatchEdge(
                edge_id="runtime-dispatch-edge-" + stable_dispatch_fingerprint(
                    {
                        "dispatch_id": record.dispatch_id,
                        "from": previous.node_id,
                        "to": node.node_id,
                        "edge_type": edge_type,
                    }
                )[:16],
                dispatch_id=record.dispatch_id,
                from_node_id=previous.node_id,
                to_node_id=node.node_id,
                edge_type=edge_type,
            )
            edges.append(edge.to_dict())

        return RuntimeDispatchRecord.from_dict(
            {
                **record.to_dict(),
                "status": status if status in {DISPATCH_STATUS_BLOCKED, DISPATCH_STATUS_FAILED, DISPATCH_STATUS_COMPLETED} else record.status,
                "nodes": [item.to_dict() for item in record.nodes] + [node.to_dict()],
                "edges": edges,
                "updated_at": utc_timestamp(),
            }
        )

    def _replace_dispatch(self, record: RuntimeDispatchRecord, **updates: Any) -> RuntimeDispatchRecord:
        latest = self._dispatches.get(record.dispatch_id, record)
        payload = latest.to_dict()
        payload.update(copy.deepcopy(updates))
        payload["updated_at"] = utc_timestamp()
        updated = RuntimeDispatchRecord.from_dict(payload)
        self._dispatches[updated.dispatch_id] = updated
        self.save()
        return copy.deepcopy(updated)

    def _append_event(self, event_type: str, *, dispatch_id: str = "", payload: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None) -> None:
        event_id = "runtime-dispatch-event-" + stable_dispatch_fingerprint(
            {"event_type": event_type, "dispatch_id": dispatch_id, "sequence": len(self._events) + 1}
        )[:16]
        event = RuntimeDispatchEvent(
            event_id=event_id,
            event_type=event_type,
            dispatch_id=str(dispatch_id or ""),
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
                    target.append_record("runtime_native_execution_dispatch", event.to_dict())
            except Exception:
                pass

    def _validate_text(self, field_name: str, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise RuntimeNativeExecutionDispatchRejected(f"{field_name}_required")
        return text
