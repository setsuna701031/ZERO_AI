from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from core.runtime.aer_runtime_integration import AERRuntimeIntegration
from core.runtime.runtime_execution_fabric import RuntimeExecutionFabric
from core.runtime.runtime_native_agent_loop import RuntimeNativeAgentLoop
from core.runtime.runtime_ownership_isolation_fabric import (
    CAPABILITY_EXECUTE,
    CAPABILITY_READ,
    CAPABILITY_WRITE,
    RuntimeOwnershipIsolationFabric,
)
from core.runtime.runtime_recovery_orchestrator import RuntimeRecoveryOrchestrator
from core.runtime.runtime_session_lease import RuntimeSessionLeaseRegistry
from core.runtime.runtime_supervisor import RuntimeSupervisor
from core.runtime.runtime_supervisor_bridge import RuntimeSupervisorBridge
from core.runtime.runtime_transaction_fabric import RuntimeTransactionFabric
from core.runtime.runtime_watchdog import RuntimeWatchdog
from core.runtime.runtime_watchdog_lease_bridge import RuntimeWatchdogLeaseBridge
from core.runtime.runtime_persistence_service import RuntimePersistenceService


MAINLINE_STATUS_READY = "ready"
MAINLINE_STATUS_RUNNING = "running"
MAINLINE_STATUS_COMPLETED = "completed"
MAINLINE_STATUS_FAILED = "failed"
MAINLINE_STATUS_BLOCKED = "blocked"

MAINLINE_MODE_RUNTIME_NATIVE = "runtime_native"
MAINLINE_MODE_LEGACY_ADAPTER = "legacy_adapter"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_mainline_fingerprint(value: Any) -> str:
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


def _list_config(data: dict[str, Any], key: str, default: list[Any]) -> list[Any]:
    if key in data:
        value = data.get(key)
        return _copy_list(value)
    return copy.deepcopy(default)


@dataclass(frozen=True)
class RuntimeNativeMainlineConfig:
    workspace_root: str = "workspace"
    runtime_id: str = "zero-runtime-native-mainline"
    namespace: str = "zero.runtime.native"
    owner_id: str = "zero-operator"
    source_session_id: str = "zero-runtime-session"
    default_task_id: str = ""
    mode: str = MAINLINE_MODE_RUNTIME_NATIVE
    max_cycles: int = 50
    auto_recover: bool = True
    capabilities: list[str] = field(default_factory=lambda: [CAPABILITY_READ, CAPABILITY_WRITE, CAPABILITY_EXECUTE])
    allowed_paths: list[str] = field(default_factory=lambda: ["aer://task/", "workspace/"])
    denied_paths: list[str] = field(default_factory=lambda: ["workspace/system/"])
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_root": self.workspace_root,
            "runtime_id": self.runtime_id,
            "namespace": self.namespace,
            "owner_id": self.owner_id,
            "source_session_id": self.source_session_id,
            "default_task_id": self.default_task_id,
            "mode": self.mode,
            "max_cycles": self.max_cycles,
            "auto_recover": self.auto_recover,
            "capabilities": copy.deepcopy(self.capabilities),
            "allowed_paths": copy.deepcopy(self.allowed_paths),
            "denied_paths": copy.deepcopy(self.denied_paths),
            "metadata": copy.deepcopy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeNativeMainlineConfig":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            workspace_root=str(data.get("workspace_root") or "workspace"),
            runtime_id=str(data.get("runtime_id") or "zero-runtime-native-mainline"),
            namespace=str(data.get("namespace") or "zero.runtime.native"),
            owner_id=str(data.get("owner_id") or "zero-operator"),
            source_session_id=str(data.get("source_session_id") or "zero-runtime-session"),
            default_task_id=str(data.get("default_task_id") or ""),
            mode=str(data.get("mode") or MAINLINE_MODE_RUNTIME_NATIVE),
            max_cycles=max(1, _safe_int(data.get("max_cycles"), 50)),
            auto_recover=bool(data.get("auto_recover", True)),
            capabilities=_list_config(data, "capabilities", [CAPABILITY_READ, CAPABILITY_WRITE, CAPABILITY_EXECUTE]),
            allowed_paths=_list_config(data, "allowed_paths", ["aer://task/", "workspace/"]),
            denied_paths=_list_config(data, "denied_paths", ["workspace/system/"]),
            metadata=_copy_dict(data.get("metadata")),
        )


@dataclass(frozen=True)
class RuntimeNativeMainlineRunResult:
    run_id: str
    status: str
    goal: str
    runtime_id: str
    source_session_id: str
    loop_id: str = ""
    task_id: str = ""
    execution_id: str = ""
    final_result: dict[str, Any] = field(default_factory=dict)
    loop_record: dict[str, Any] = field(default_factory=dict)
    authority_decision: dict[str, Any] = field(default_factory=dict)
    recovery_tickets: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "goal": self.goal,
            "runtime_id": self.runtime_id,
            "source_session_id": self.source_session_id,
            "loop_id": self.loop_id,
            "task_id": self.task_id,
            "execution_id": self.execution_id,
            "final_result": copy.deepcopy(self.final_result),
            "loop_record": copy.deepcopy(self.loop_record),
            "authority_decision": copy.deepcopy(self.authority_decision),
            "recovery_tickets": copy.deepcopy(self.recovery_tickets),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeNativeMainlineRunResult":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            run_id=str(data.get("run_id") or ""),
            status=str(data.get("status") or MAINLINE_STATUS_READY),
            goal=str(data.get("goal") or ""),
            runtime_id=str(data.get("runtime_id") or ""),
            source_session_id=str(data.get("source_session_id") or ""),
            loop_id=str(data.get("loop_id") or ""),
            task_id=str(data.get("task_id") or ""),
            execution_id=str(data.get("execution_id") or ""),
            final_result=_copy_dict(data.get("final_result")),
            loop_record=_copy_dict(data.get("loop_record")),
            authority_decision=_copy_dict(data.get("authority_decision")),
            recovery_tickets=_copy_list(data.get("recovery_tickets")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeNativeMainlineEvent:
    event_id: str
    event_type: str
    run_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "run_id": self.run_id,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "timestamp": self.timestamp,
            "source": "runtime_native_mainline",
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeNativeMainlineEvent":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            event_id=str(data.get("event_id") or ""),
            event_type=str(data.get("event_type") or ""),
            run_id=str(data.get("run_id") or ""),
            payload=_copy_dict(data.get("payload")),
            metadata=_copy_dict(data.get("metadata")),
            timestamp=str(data.get("timestamp") or utc_timestamp()),
        )


class RuntimeNativeMainlineRejected(RuntimeError):
    pass


PlannerFn = Callable[[str, dict[str, Any]], dict[str, Any]]
StepRunnerFn = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


class RuntimeNativeMainline:
    """
    Runtime-native mainline facade.

    Migration surface for app.py / scheduler.py / agent_loop.py:
      - boot sealed runtime core
      - register runtime ownership
      - register session lease/watchdog
      - run goal through runtime-native loop
      - preserve recovery/continuation/replay lineage
      - expose stable call: run_goal(...)
    """

    def __init__(
        self,
        *,
        config: RuntimeNativeMainlineConfig | dict[str, Any] | None = None,
        storage_path: str | Path | None = None,
        orchestrator: RuntimeRecoveryOrchestrator | None = None,
        lease_registry: RuntimeSessionLeaseRegistry | None = None,
        watchdog: RuntimeWatchdog | None = None,
        watchdog_lease_bridge: RuntimeWatchdogLeaseBridge | None = None,
        supervisor: RuntimeSupervisor | None = None,
        supervisor_bridge: RuntimeSupervisorBridge | None = None,
        execution_fabric: RuntimeExecutionFabric | None = None,
        transaction_fabric: RuntimeTransactionFabric | None = None,
        ownership_fabric: RuntimeOwnershipIsolationFabric | None = None,
        aer_integration: AERRuntimeIntegration | None = None,
        runtime_loop: RuntimeNativeAgentLoop | None = None,
        journal: Any = None,
        audit: Any = None,
    ) -> None:
        if isinstance(config, RuntimeNativeMainlineConfig):
            self.config = config
        else:
            self.config = RuntimeNativeMainlineConfig.from_dict(config or {})

        self.workspace_root = Path(self.config.workspace_root)
        self.storage_path = Path(storage_path) if storage_path is not None else self.workspace_root / "runtime_native_mainline" / "runtime_native_mainline.json"
        self.journal = journal
        self.audit = audit
        self.persistence_service = RuntimePersistenceService(
            workspace_root=(self.storage_path.parent if self.storage_path is not None else "workspace"),
            source="runtime_native_mainline",
        )

        self.orchestrator = orchestrator
        self.lease_registry = lease_registry
        self.watchdog = watchdog
        self.watchdog_lease_bridge = watchdog_lease_bridge
        self.supervisor = supervisor
        self.supervisor_bridge = supervisor_bridge
        self.execution_fabric = execution_fabric
        self.transaction_fabric = transaction_fabric
        self.ownership_fabric = ownership_fabric
        self.aer_integration = aer_integration
        self.runtime_loop = runtime_loop

        self._runs: dict[str, RuntimeNativeMainlineRunResult] = {}
        self._run_order: list[str] = []
        self._events: list[RuntimeNativeMainlineEvent] = []

        self._booted = False
        self.load()

    @classmethod
    def with_workspace(
        cls,
        workspace_root: str | Path = "workspace",
        **kwargs: Any,
    ) -> "RuntimeNativeMainline":
        config = kwargs.pop("config", None)
        if isinstance(config, RuntimeNativeMainlineConfig):
            cfg = RuntimeNativeMainlineConfig.from_dict({**config.to_dict(), "workspace_root": str(workspace_root)})
        else:
            cfg = RuntimeNativeMainlineConfig.from_dict({**(config or {}), "workspace_root": str(workspace_root)})
        return cls(config=cfg, **kwargs)

    def boot(self) -> "RuntimeNativeMainline":
        root = self.workspace_root
        root.mkdir(parents=True, exist_ok=True)

        if self.orchestrator is None:
            self.orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
                root / "recovery",
                runner=lambda payload: {
                    "ok": True,
                    "status": "completed",
                    "execution_id": "runtime-native-mainline-recovery",
                    "replay_id": "runtime-native-mainline-replay",
                },
            )

        if self.lease_registry is None:
            self.lease_registry = RuntimeSessionLeaseRegistry.with_workspace(
                root / "lease",
                default_ttl_ticks=5,
                zombie_after_ticks=20,
            )

        if self.watchdog is None:
            self.watchdog = RuntimeWatchdog.with_workspace(
                root / "watchdog",
                stall_after_ticks=3,
                dead_after_ticks=10,
            )

        if self.watchdog_lease_bridge is None:
            self.watchdog_lease_bridge = RuntimeWatchdogLeaseBridge(
                lease_registry=self.lease_registry,
                watchdog=self.watchdog,
                orchestrator=None,
            )

        if self.supervisor is None:
            self.supervisor = RuntimeSupervisor.with_workspace(
                root / "supervisor",
                orchestrator=self.orchestrator,
                lease_registry=self.lease_registry,
            )

        if self.supervisor_bridge is None:
            self.supervisor_bridge = RuntimeSupervisorBridge.with_workspace(
                root / "supervisor_bridge",
                watchdog_lease_bridge=self.watchdog_lease_bridge,
                supervisor=self.supervisor,
                recovery_orchestrator=self.orchestrator,
            )

        if self.execution_fabric is None:
            self.execution_fabric = RuntimeExecutionFabric.with_workspace(
                root / "execution",
                recovery_orchestrator=self.orchestrator,
                supervisor=self.supervisor,
            )

        if self.transaction_fabric is None:
            self.transaction_fabric = RuntimeTransactionFabric.with_workspace(
                root / "transaction",
                recovery_orchestrator=self.orchestrator,
                execution_fabric=self.execution_fabric,
            )

        if self.ownership_fabric is None:
            self.ownership_fabric = RuntimeOwnershipIsolationFabric.with_workspace(root / "ownership")

        self._ensure_runtime_registered()
        self._ensure_session_registered(current_tick=1)

        if self.aer_integration is None:
            self.aer_integration = AERRuntimeIntegration.with_workspace(
                root / "aer_integration",
                recovery_orchestrator=self.orchestrator,
                execution_fabric=self.execution_fabric,
                transaction_fabric=self.transaction_fabric,
                ownership_fabric=self.ownership_fabric,
                supervisor_bridge=self.supervisor_bridge,
            )

        if self.runtime_loop is None:
            self.runtime_loop = RuntimeNativeAgentLoop.with_workspace(
                root / "runtime_loop",
                aer_integration=self.aer_integration,
                supervisor_bridge=self.supervisor_bridge,
                ownership_fabric=self.ownership_fabric,
            )

        self._booted = True
        self._append_event("runtime_native_mainline_booted", payload={"config": self.config.to_dict()})
        self.save()
        return self

    def run_goal(
        self,
        goal: str,
        *,
        planner_fn: PlannerFn | None = None,
        step_runner: StepRunnerFn | None = None,
        resume_runner: StepRunnerFn | None = None,
        current_tick: int = 2,
        task_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeNativeMainlineRunResult:
        if not self._booted:
            self.boot()

        goal = self._validate_text("goal", goal)
        run_id = "runtime-native-mainline-run-" + stable_mainline_fingerprint(
            {
                "goal": goal,
                "runtime_id": self.config.runtime_id,
                "source_session_id": self.config.source_session_id,
                "sequence": len(self._runs) + 1,
            }
        )[:16]

        authority = self.ownership_fabric.authorize(
            runtime_id=self.config.runtime_id,
            capability=CAPABILITY_EXECUTE,
            target=f"aer://task/{task_id or run_id}",
            owner_id=self.config.owner_id,
        )
        authority_payload = authority.to_dict() if hasattr(authority, "to_dict") else copy.deepcopy(authority)

        if str(authority_payload.get("decision") or "") != "allow":
            result = RuntimeNativeMainlineRunResult(
                run_id=run_id,
                status=MAINLINE_STATUS_BLOCKED,
                goal=goal,
                runtime_id=self.config.runtime_id,
                source_session_id=self.config.source_session_id,
                authority_decision=authority_payload,
                metadata=copy.deepcopy(metadata or {}),
            )
            self._store_result(result)
            self._append_event("runtime_native_mainline_blocked", run_id=run_id, payload={"result": result.to_dict()})
            return result

        loop = self.runtime_loop.create_loop(
            source_session_id=self.config.source_session_id,
            runtime_id=self.config.runtime_id,
            owner_id=self.config.owner_id,
            task_id=task_id or self.config.default_task_id,
            max_cycles=self.config.max_cycles,
            auto_recover=self.config.auto_recover,
            metadata=copy.deepcopy(metadata or {}),
        )

        try:
            completed_loop = self.runtime_loop.run_goal(
                loop.loop_id,
                goal=goal,
                planner_fn=planner_fn,
                step_runner=step_runner,
                resume_runner=resume_runner,
                current_tick=current_tick,
            )
            loop_payload = completed_loop.to_dict() if hasattr(completed_loop, "to_dict") else copy.deepcopy(completed_loop)
            task_payload = _copy_dict(loop_payload.get("task"))
            status = MAINLINE_STATUS_COMPLETED if str(loop_payload.get("status") or "") == "completed" else MAINLINE_STATUS_FAILED

            result = RuntimeNativeMainlineRunResult(
                run_id=run_id,
                status=status,
                goal=goal,
                runtime_id=self.config.runtime_id,
                source_session_id=self.config.source_session_id,
                loop_id=str(loop_payload.get("loop_id") or ""),
                task_id=str(task_payload.get("task_id") or ""),
                execution_id=str(task_payload.get("execution_id") or ""),
                final_result=_copy_dict(loop_payload.get("final_result")),
                loop_record=loop_payload,
                authority_decision=authority_payload,
                recovery_tickets=[
                    ticket.to_dict() if hasattr(ticket, "to_dict") else copy.deepcopy(ticket)
                    for ticket in self.orchestrator.queue.list_tickets()
                ],
                metadata=copy.deepcopy(metadata or {}),
            )
        except Exception as exc:
            result = RuntimeNativeMainlineRunResult(
                run_id=run_id,
                status=MAINLINE_STATUS_FAILED,
                goal=goal,
                runtime_id=self.config.runtime_id,
                source_session_id=self.config.source_session_id,
                loop_id=loop.loop_id,
                authority_decision=authority_payload,
                final_result={"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}},
                metadata=copy.deepcopy(metadata or {}),
            )

        self._store_result(result)
        self._append_event("runtime_native_mainline_run_completed", run_id=run_id, payload={"result": result.to_dict()})
        self.save()
        return copy.deepcopy(result)

    def run_legacy_request(
        self,
        request: dict[str, Any],
        *,
        planner_fn: PlannerFn | None = None,
        step_runner: StepRunnerFn | None = None,
        resume_runner: StepRunnerFn | None = None,
        current_tick: int = 2,
    ) -> RuntimeNativeMainlineRunResult:
        payload = request if isinstance(request, dict) else {}
        goal = str(payload.get("goal") or payload.get("prompt") or payload.get("task") or "").strip()
        if not goal:
            raise RuntimeNativeMainlineRejected("legacy_request_goal_required")

        return self.run_goal(
            goal,
            planner_fn=planner_fn,
            step_runner=step_runner,
            resume_runner=resume_runner,
            current_tick=current_tick,
            task_id=str(payload.get("task_id") or ""),
            metadata={"legacy_request": copy.deepcopy(payload)},
        )

    def health(self) -> dict[str, Any]:
        if not self._booted:
            self.boot()

        return {
            "ok": True,
            "runtime_phase": "runtime_native_mainline_health",
            "config": self.config.to_dict(),
            "runs": len(self._runs),
            "events": len(self._events),
            "queue_tickets": len(self.orchestrator.queue.list_tickets()) if self.orchestrator is not None else 0,
            "lease_sessions": len(self.lease_registry.list_sessions()) if self.lease_registry is not None else 0,
            "watchdog_sessions": len(self.watchdog.list_sessions()) if self.watchdog is not None else 0,
            "supervisor_cases": len(self.supervisor.list_cases()) if self.supervisor is not None else 0,
            "execution_records": len(self.execution_fabric.list_executions()) if self.execution_fabric is not None else 0,
            "mainline_status": MAINLINE_STATUS_READY,
        }

    def latest_result(self) -> RuntimeNativeMainlineRunResult | None:
        if not self._run_order:
            return None
        return copy.deepcopy(self._runs[self._run_order[-1]])

    def list_results(self) -> list[RuntimeNativeMainlineRunResult]:
        return [copy.deepcopy(self._runs[run_id]) for run_id in self._run_order if run_id in self._runs]

    def list_events(self) -> list[RuntimeNativeMainlineEvent]:
        return [copy.deepcopy(event) for event in self._events]

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_phase": "runtime_native_mainline",
            "config": self.config.to_dict(),
            "runs": [self._runs[run_id].to_dict() for run_id in self._run_order if run_id in self._runs],
            "events": [event.to_dict() for event in self._events[-500:]],
        }

    def load(self) -> None:
        if self.storage_path is None or not self.storage_path.exists():
            return
        try:
            payload = self.persistence_service.read_json(
                self.storage_path,
                default={},
            )
        except Exception:
            return
        if not isinstance(payload, dict):
            return

        self._runs = {}
        self._run_order = []
        self._events = []

        config_payload = payload.get("config")
        if isinstance(config_payload, dict):
            self.config = RuntimeNativeMainlineConfig.from_dict(config_payload)

        for item in payload.get("runs") or []:
            if isinstance(item, dict):
                result = RuntimeNativeMainlineRunResult.from_dict(item)
                if result.run_id:
                    self._runs[result.run_id] = result
                    self._run_order.append(result.run_id)

        for item in payload.get("events") or []:
            if isinstance(item, dict):
                event = RuntimeNativeMainlineEvent.from_dict(item)
                if event.event_id:
                    self._events.append(event)

    def save(self) -> None:
        if self.storage_path is None:
            return
        self.persistence_service.write_json(
            self.storage_path,
            self.to_dict(),
            reason="runtime_native_mainline_save",
            metadata={"runtime_native_mainline": True},
        )

    def _ensure_runtime_registered(self) -> None:
        try:
            self.ownership_fabric.get_runtime(self.config.runtime_id)
            return
        except Exception:
            pass

        self.ownership_fabric.register_runtime(
            runtime_id=self.config.runtime_id,
            namespace=self.config.namespace,
            owner_id=self.config.owner_id,
            session_ids=[self.config.source_session_id],
            capabilities=copy.deepcopy(self.config.capabilities),
            allowed_paths=copy.deepcopy(self.config.allowed_paths),
            denied_paths=copy.deepcopy(self.config.denied_paths),
            metadata={"registered_by": "runtime_native_mainline"},
        )

    def _ensure_session_registered(self, *, current_tick: int) -> None:
        try:
            self.lease_registry.get_session(self.config.source_session_id)
            return
        except Exception:
            pass

        self.supervisor_bridge.register_session(
            self.config.source_session_id,
            self.config.owner_id,
            task_id=self.config.default_task_id,
            current_tick=current_tick,
        )

    def _store_result(self, result: RuntimeNativeMainlineRunResult) -> None:
        self._runs[result.run_id] = result
        if result.run_id not in self._run_order:
            self._run_order.append(result.run_id)
        self.save()

    def _append_event(self, event_type: str, *, run_id: str = "", payload: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None) -> None:
        event_id = "runtime-native-mainline-event-" + stable_mainline_fingerprint(
            {"event_type": event_type, "run_id": run_id, "sequence": len(self._events) + 1}
        )[:16]
        event = RuntimeNativeMainlineEvent(
            event_id=event_id,
            event_type=event_type,
            run_id=str(run_id or ""),
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
                    target.append_record("runtime_native_mainline", event.to_dict())
            except Exception:
                pass

    def _validate_text(self, field_name: str, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise RuntimeNativeMainlineRejected(f"{field_name}_required")
        return text
