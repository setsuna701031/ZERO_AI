from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from core.runtime.runtime_persistence_service import RuntimePersistenceService
from core.runtime.runtime_native_execution_authority import runtime_native_execution_path


LOOP_STATUS_CREATED = "created"
LOOP_STATUS_RUNNING = "running"
LOOP_STATUS_WAITING_RECOVERY = "waiting_recovery"
LOOP_STATUS_RECOVERED = "recovered"
LOOP_STATUS_COMPLETED = "completed"
LOOP_STATUS_FAILED = "failed"
LOOP_STATUS_BLOCKED = "blocked"

LOOP_EVENT_CREATED = "runtime_native_agent_loop_created"
LOOP_EVENT_STARTED = "runtime_native_agent_loop_started"
LOOP_EVENT_TASK_ACCEPTED = "runtime_native_agent_loop_task_accepted"
LOOP_EVENT_TASK_PLANNED = "runtime_native_agent_loop_task_planned"
LOOP_EVENT_STEP_EXECUTED = "runtime_native_agent_loop_step_executed"
LOOP_EVENT_FAILURE_RECOVERED = "runtime_native_agent_loop_failure_recovered"
LOOP_EVENT_COMPLETED = "runtime_native_agent_loop_completed"
LOOP_EVENT_BLOCKED = "runtime_native_agent_loop_blocked"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_loop_fingerprint(value: Any) -> str:
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
class RuntimeNativeAgentLoopConfig:
    loop_id: str
    runtime_id: str = ""
    owner_id: str = ""
    source_session_id: str = ""
    task_id: str = ""
    max_cycles: int = 20
    auto_recover: bool = True
    stop_on_blocked: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "loop_id": self.loop_id,
            "runtime_id": self.runtime_id,
            "owner_id": self.owner_id,
            "source_session_id": self.source_session_id,
            "task_id": self.task_id,
            "max_cycles": self.max_cycles,
            "auto_recover": self.auto_recover,
            "stop_on_blocked": self.stop_on_blocked,
            "metadata": copy.deepcopy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeNativeAgentLoopConfig":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            loop_id=str(data.get("loop_id") or ""),
            runtime_id=str(data.get("runtime_id") or ""),
            owner_id=str(data.get("owner_id") or ""),
            source_session_id=str(data.get("source_session_id") or ""),
            task_id=str(data.get("task_id") or ""),
            max_cycles=max(1, _safe_int(data.get("max_cycles"), 20)),
            auto_recover=bool(data.get("auto_recover", True)),
            stop_on_blocked=bool(data.get("stop_on_blocked", True)),
            metadata=_copy_dict(data.get("metadata")),
        )


@dataclass(frozen=True)
class RuntimeNativeAgentLoopCycle:
    cycle_id: str
    loop_id: str
    cycle_index: int
    task_id: str = ""
    execution_id: str = ""
    status: str = LOOP_STATUS_RUNNING
    step: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    recovery_ref: dict[str, Any] = field(default_factory=dict)
    continuation_ref: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "loop_id": self.loop_id,
            "cycle_index": self.cycle_index,
            "task_id": self.task_id,
            "execution_id": self.execution_id,
            "status": self.status,
            "step": copy.deepcopy(self.step),
            "result": copy.deepcopy(self.result),
            "recovery_ref": copy.deepcopy(self.recovery_ref),
            "continuation_ref": copy.deepcopy(self.continuation_ref),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeNativeAgentLoopCycle":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            cycle_id=str(data.get("cycle_id") or ""),
            loop_id=str(data.get("loop_id") or ""),
            cycle_index=_safe_int(data.get("cycle_index"), 0),
            task_id=str(data.get("task_id") or ""),
            execution_id=str(data.get("execution_id") or ""),
            status=str(data.get("status") or LOOP_STATUS_RUNNING),
            step=_copy_dict(data.get("step")),
            result=_copy_dict(data.get("result")),
            recovery_ref=_copy_dict(data.get("recovery_ref")),
            continuation_ref=_copy_dict(data.get("continuation_ref")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeNativeAgentLoopRecord:
    loop_id: str
    status: str
    config: dict[str, Any] = field(default_factory=dict)
    task: dict[str, Any] = field(default_factory=dict)
    cycles: list[RuntimeNativeAgentLoopCycle] = field(default_factory=list)
    final_result: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "loop_id": self.loop_id,
            "status": self.status,
            "config": copy.deepcopy(self.config),
            "task": copy.deepcopy(self.task),
            "cycles": [cycle.to_dict() for cycle in self.cycles],
            "final_result": copy.deepcopy(self.final_result),
            "metadata": copy.deepcopy(self.metadata),
            "execution_path": runtime_native_execution_path(
                entrypoint="runtime_native_agent_loop.run_goal",
                delegation_only=True,
            ),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeNativeAgentLoopRecord":
        data = payload if isinstance(payload, dict) else {}
        cycles = []
        for item in data.get("cycles") or []:
            if isinstance(item, dict):
                cycles.append(RuntimeNativeAgentLoopCycle.from_dict(item))
        return cls(
            loop_id=str(data.get("loop_id") or ""),
            status=str(data.get("status") or LOOP_STATUS_CREATED),
            config=_copy_dict(data.get("config")),
            task=_copy_dict(data.get("task")),
            cycles=cycles,
            final_result=_copy_dict(data.get("final_result")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeNativeAgentLoopEvent:
    event_id: str
    event_type: str
    loop_id: str = ""
    task_id: str = ""
    execution_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "loop_id": self.loop_id,
            "task_id": self.task_id,
            "execution_id": self.execution_id,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "timestamp": self.timestamp,
            "source": "runtime_native_agent_loop",
        }


class RuntimeNativeAgentLoopRejected(RuntimeError):
    pass


PlannerFn = Callable[[str, dict[str, Any]], dict[str, Any]]
StepRunnerFn = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]

class _RuntimeNativeAgentLoopDispatcherAdapter:
    """RuntimeNativeAgentLoop-owned dispatcher endpoint for AER handoff tests/mainline.

    The adapter gives AERRuntimeIntegration a RuntimeDispatcher-shaped boundary
    without letting AER execute steps directly or construct its own runtime stack.
    The active step runner is bound by RuntimeNativeAgentLoop.run_goal() for the
    current run only.
    """

    def __init__(self) -> None:
        self._step_runner: StepRunnerFn | None = None

    def bind_step_runner(self, runner: StepRunnerFn | None) -> None:
        self._step_runner = runner

    def clear_step_runner(self) -> None:
        self._step_runner = None

    def run_scheduler_boundary(self, task: dict[str, Any], *, current_tick: int = 0) -> dict[str, Any]:
        boundary_task = copy.deepcopy(task) if isinstance(task, dict) else {}
        steps = boundary_task.get("steps") if isinstance(boundary_task.get("steps"), list) else []
        step_index = _safe_int(boundary_task.get("current_step_index"), _safe_int(current_tick, 0))
        if step_index < 0:
            step_index = 0
        step = copy.deepcopy(steps[step_index]) if step_index < len(steps) and isinstance(steps[step_index], dict) else {}

        runner = self._step_runner
        if runner is None:
            endpoint_result = {
                "ok": False,
                "failed": True,
                "blocked": True,
                "status": "blocked",
                "error": "runtime_native_step_runner_required",
            }
        else:
            context = {
                "task": copy.deepcopy(boundary_task),
                "execution_id": str(boundary_task.get("aer_execution_id") or ""),
                "runtime_native_dispatcher_adapter": True,
                "runtime_dispatcher_handoff": True,
                "authority_propagation_required": True,
            }
            result = runner(copy.deepcopy(step), context)
            endpoint_result = result if isinstance(result, dict) else {"ok": True, "result": copy.deepcopy(result)}
            endpoint_result = copy.deepcopy(endpoint_result)

        failed = bool(endpoint_result.get("failed", False)) or not bool(endpoint_result.get("ok", True))
        status = str(endpoint_result.get("status") or ("failed" if failed else "completed")).strip().lower()
        if status in {"failed", "blocked", "cancelled"}:
            failed = True
        endpoint_result.setdefault("ok", not failed)
        endpoint_result.setdefault("failed", failed)
        endpoint_result["status"] = status
        endpoint_result.setdefault("step", copy.deepcopy(step))
        endpoint_result.setdefault("runtime_dispatcher_handoff", True)
        endpoint_result.setdefault("runtime_native_dispatcher_adapter", True)

        return {
            "ok": not failed,
            "status": status,
            "runtime_state": {
                "status": status,
                "final_result": copy.deepcopy(endpoint_result),
                "step_results": [copy.deepcopy(endpoint_result)],
                "execution_trace": [
                    {
                        "step_index": step_index,
                        "step": copy.deepcopy(step),
                        "result": copy.deepcopy(endpoint_result),
                        "runtime_dispatcher_handoff": True,
                        "runtime_native_dispatcher_adapter": True,
                    }
                ],
            },
            "final_result": copy.deepcopy(endpoint_result),
            "execution_path": {
                "authority_path": "AERRuntimeIntegration -> RuntimeDispatcher -> TaskRunner -> StepExecutor",
                "runtime_dispatcher_handoff": True,
                "runtime_native_dispatcher_adapter": True,
                "direct_execution": False,
            },
        }


class RuntimeNativeAgentLoop:
    """
    Runtime-native agent loop adapter.

    This does not replace the old agent_loop.py. It provides a runtime-native
    mainline that can later be wired into app/scheduler/agent_loop without
    bloating those modules.
    """

    def __init__(
        self,
        *,
        storage_path: str | Path | None = None,
        aer_integration: Any,
        supervisor_bridge: Any = None,
        ownership_fabric: Any = None,
        journal: Any = None,
        audit: Any = None,
    ) -> None:
        if aer_integration is None:
            raise RuntimeNativeAgentLoopRejected("aer_integration_required")
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self.aer_integration = aer_integration
        self._runtime_dispatcher_adapter = None
        if getattr(self.aer_integration, "runtime_dispatcher", None) is None:
            self._runtime_dispatcher_adapter = _RuntimeNativeAgentLoopDispatcherAdapter()
            setattr(self.aer_integration, "runtime_dispatcher", self._runtime_dispatcher_adapter)
        else:
            dispatcher = getattr(self.aer_integration, "runtime_dispatcher", None)
            if all(hasattr(dispatcher, name) for name in ("bind_step_runner", "clear_step_runner")):
                self._runtime_dispatcher_adapter = dispatcher
        self.supervisor_bridge = supervisor_bridge
        self.ownership_fabric = ownership_fabric
        self.journal = journal
        self.audit = audit
        self.persistence_service = RuntimePersistenceService(
            workspace_root=(self.storage_path.parent if self.storage_path is not None else "workspace"),
            source="runtime_native_agent_loop",
        )
        self._loops: dict[str, RuntimeNativeAgentLoopRecord] = {}
        self._loop_order: list[str] = []
        self._events: list[RuntimeNativeAgentLoopEvent] = []
        if self.storage_path is not None:
            self.load()

    @classmethod
    def with_workspace(
        cls,
        workspace_root: str | Path = "workspace",
        **kwargs: Any,
    ) -> "RuntimeNativeAgentLoop":
        root = Path(workspace_root)
        loop_dir = root / "runtime_native_agent_loop"
        loop_dir.mkdir(parents=True, exist_ok=True)
        return cls(storage_path=loop_dir / "runtime_native_agent_loop.json", **kwargs)

    def create_loop(
        self,
        *,
        source_session_id: str,
        runtime_id: str = "",
        owner_id: str = "",
        task_id: str = "",
        max_cycles: int = 20,
        auto_recover: bool = True,
        metadata: dict[str, Any] | None = None,
        loop_id: str | None = None,
    ) -> RuntimeNativeAgentLoopRecord:
        source_session_id = self._validate_text("source_session_id", source_session_id)
        if loop_id is None:
            loop_id = "runtime-native-loop-" + stable_loop_fingerprint(
                {
                    "source_session_id": source_session_id,
                    "runtime_id": runtime_id,
                    "owner_id": owner_id,
                    "task_id": task_id,
                    "metadata": metadata or {},
                }
            )[:16]
        loop_id = self._validate_text("loop_id", loop_id)
        if loop_id in self._loops:
            raise RuntimeNativeAgentLoopRejected(f"runtime native loop already exists: {loop_id!r}")

        config = RuntimeNativeAgentLoopConfig(
            loop_id=loop_id,
            runtime_id=str(runtime_id or ""),
            owner_id=str(owner_id or ""),
            source_session_id=source_session_id,
            task_id=str(task_id or ""),
            max_cycles=max(1, int(max_cycles)),
            auto_recover=bool(auto_recover),
            metadata=copy.deepcopy(metadata or {}),
        )
        record = RuntimeNativeAgentLoopRecord(
            loop_id=loop_id,
            status=LOOP_STATUS_CREATED,
            config=config.to_dict(),
            metadata=copy.deepcopy(metadata or {}),
        )
        self._loops[loop_id] = record
        self._loop_order.append(loop_id)
        self._append_event(
            LOOP_EVENT_CREATED,
            loop_id=loop_id,
            payload={"loop": record.to_dict()},
        )
        self.save()
        return copy.deepcopy(record)

    def run_goal(
        self,
        loop_id: str,
        *,
        goal: str,
        planner_fn: PlannerFn | None = None,
        step_runner: StepRunnerFn | None = None,
        resume_runner: StepRunnerFn | None = None,
        current_tick: int = 0,
    ) -> RuntimeNativeAgentLoopRecord:
        loop = self.get_loop(loop_id)
        config = RuntimeNativeAgentLoopConfig.from_dict(loop.config)

        self._heartbeat(config, current_tick=current_tick)

        task = self.aer_integration.accept_task(
            goal=goal,
            source_session_id=config.source_session_id,
            runtime_id=config.runtime_id,
            task_id=config.task_id or None,
            metadata={
                **copy.deepcopy(config.metadata),
                "owner_id": config.owner_id,
                "loop_id": loop_id,
            },
        )
        task_payload = task.to_dict() if hasattr(task, "to_dict") else copy.deepcopy(task)
        loop = self._replace_loop(
            self.get_loop(loop_id),
            status=LOOP_STATUS_RUNNING,
            task=task_payload,
        )
        self._append_event(
            LOOP_EVENT_TASK_ACCEPTED,
            loop_id=loop_id,
            task_id=str(task_payload.get("task_id") or ""),
            payload={"task": task_payload},
        )

        planned = self.aer_integration.plan_task(
            task_payload["task_id"],
            planner_fn=planner_fn,
        )
        planned_payload = planned.to_dict() if hasattr(planned, "to_dict") else copy.deepcopy(planned)
        loop = self._replace_loop(self.get_loop(loop_id), task=planned_payload)
        self._append_event(
            LOOP_EVENT_TASK_PLANNED,
            loop_id=loop_id,
            task_id=planned_payload["task_id"],
            payload={"task": planned_payload},
        )

        started = self.aer_integration.start_execution(planned_payload["task_id"])
        task_payload = started.to_dict() if hasattr(started, "to_dict") else copy.deepcopy(started)
        loop = self._replace_loop(self.get_loop(loop_id), task=task_payload)
        self._append_event(
            LOOP_EVENT_STARTED,
            loop_id=loop_id,
            task_id=task_payload["task_id"],
            execution_id=task_payload.get("execution_id", ""),
            payload={"task": task_payload},
        )

        run_step_runner = self._cycle_runner(
            loop_id=loop_id,
            base_runner=step_runner,
        )
        self._bind_runtime_dispatcher_runner(run_step_runner)
        try:
            ran = self.aer_integration.run_task(
                task_payload["task_id"],
                step_runner=run_step_runner,
            )
        finally:
            self._clear_runtime_dispatcher_runner()
        ran_payload = ran.to_dict() if hasattr(ran, "to_dict") else copy.deepcopy(ran)
        loop = self._replace_loop(self.get_loop(loop_id), task=ran_payload)

        if str(ran_payload.get("status") or "") == "failed":
            if not config.auto_recover:
                loop = self._replace_loop(
                    self.get_loop(loop_id),
                    status=LOOP_STATUS_FAILED,
                    final_result=copy.deepcopy(ran_payload.get("final_result") or {}),
                )
                self.save()
                return loop

            recovered = self.aer_integration.recover_task(
                ran_payload["task_id"],
                current_tick=current_tick,
                reason="runtime-native agent loop recovery",
            )
            recovered_payload = recovered.to_dict() if hasattr(recovered, "to_dict") else copy.deepcopy(recovered)
            loop = self._replace_loop(
                self.get_loop(loop_id),
                status=LOOP_STATUS_RECOVERED,
                task=recovered_payload,
            )
            self._append_event(
                LOOP_EVENT_FAILURE_RECOVERED,
                loop_id=loop_id,
                task_id=recovered_payload["task_id"],
                execution_id=recovered_payload.get("execution_id", ""),
                payload={"task": recovered_payload},
            )

            resume_step_runner = self._cycle_runner(
                loop_id=loop_id,
                base_runner=resume_runner or step_runner,
            )
            self._bind_runtime_dispatcher_runner(resume_step_runner)
            try:
                resumed = self.aer_integration.resume_task(
                    recovered_payload["task_id"],
                    step_runner=resume_step_runner,
                )
            finally:
                self._clear_runtime_dispatcher_runner()
            final_payload = resumed.to_dict() if hasattr(resumed, "to_dict") else copy.deepcopy(resumed)
        else:
            final_payload = ran_payload

        final_status = LOOP_STATUS_COMPLETED if str(final_payload.get("status") or "") == "completed" else LOOP_STATUS_FAILED
        loop = self._replace_loop(
            self.get_loop(loop_id),
            status=final_status,
            task=final_payload,
            final_result=copy.deepcopy(final_payload.get("final_result") or {}),
        )
        self._append_event(
            LOOP_EVENT_COMPLETED if final_status == LOOP_STATUS_COMPLETED else LOOP_EVENT_BLOCKED,
            loop_id=loop_id,
            task_id=final_payload.get("task_id", ""),
            execution_id=final_payload.get("execution_id", ""),
            payload={"loop": loop.to_dict(), "task": final_payload},
        )
        self._heartbeat(config, current_tick=current_tick + 1)
        self.save()
        return copy.deepcopy(loop)

    def get_loop(self, loop_id: str) -> RuntimeNativeAgentLoopRecord:
        loop_id = self._validate_text("loop_id", loop_id)
        loop = self._loops.get(loop_id)
        if loop is None:
            raise RuntimeNativeAgentLoopRejected(f"runtime native loop does not exist: {loop_id!r}")
        return copy.deepcopy(loop)

    def list_loops(self) -> list[RuntimeNativeAgentLoopRecord]:
        return [
            copy.deepcopy(self._loops[loop_id])
            for loop_id in self._loop_order
            if loop_id in self._loops
        ]

    def list_events(self) -> list[RuntimeNativeAgentLoopEvent]:
        return [copy.deepcopy(event) for event in self._events]

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_phase": "runtime_native_agent_loop",
            "loops": [
                self._loops[loop_id].to_dict()
                for loop_id in self._loop_order
                if loop_id in self._loops
            ],
            "events": [event.to_dict() for event in self._events[-500:]],
        }

    def load(self) -> None:
        if self.storage_path is None:
            return
        if not self.storage_path.exists():
            self._loops = {}
            self._loop_order = []
            self._events = []
            return

        payload = self.persistence_service.read_json(
            self.storage_path,
            default={},
        )
        self._loops = {}
        self._loop_order = []
        self._events = []
        if not isinstance(payload, dict):
            return

        for item in payload.get("loops") or []:
            if isinstance(item, dict):
                loop = RuntimeNativeAgentLoopRecord.from_dict(item)
                if loop.loop_id:
                    self._loops[loop.loop_id] = loop
                    self._loop_order.append(loop.loop_id)

        for item in payload.get("events") or []:
            if isinstance(item, dict):
                event = RuntimeNativeAgentLoopEvent(
                    event_id=str(item.get("event_id") or ""),
                    event_type=str(item.get("event_type") or ""),
                    loop_id=str(item.get("loop_id") or ""),
                    task_id=str(item.get("task_id") or ""),
                    execution_id=str(item.get("execution_id") or ""),
                    payload=_copy_dict(item.get("payload")),
                    metadata=_copy_dict(item.get("metadata")),
                    timestamp=str(item.get("timestamp") or utc_timestamp()),
                )
                if event.event_id:
                    self._events.append(event)

    def save(self) -> None:
        if self.storage_path is None:
            return
        self.persistence_service.write_json(
            self.storage_path,
            self.to_dict(),
            reason="runtime_native_agent_loop_save",
            metadata={"runtime_native_agent_loop": True},
        )


    def _bind_runtime_dispatcher_runner(self, runner: StepRunnerFn | None) -> None:
        adapter = self._runtime_dispatcher_adapter
        bind = getattr(adapter, "bind_step_runner", None)
        if callable(bind):
            bind(runner)

    def _clear_runtime_dispatcher_runner(self) -> None:
        adapter = self._runtime_dispatcher_adapter
        clear = getattr(adapter, "clear_step_runner", None)
        if callable(clear):
            clear()

    def _cycle_runner(
        self,
        *,
        loop_id: str,
        base_runner: StepRunnerFn | None,
    ) -> StepRunnerFn:
        def runner(step: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
            loop = self.get_loop(loop_id)
            cycle_index = len(loop.cycles) + 1
            result = base_runner(copy.deepcopy(step), copy.deepcopy(context)) if base_runner is not None else {"ok": True}
            if not isinstance(result, dict):
                result = {"ok": True, "result": copy.deepcopy(result)}
            status = LOOP_STATUS_FAILED if bool(result.get("failed", False)) or not bool(result.get("ok", True)) else LOOP_STATUS_RUNNING
            cycle = RuntimeNativeAgentLoopCycle(
                cycle_id="runtime-native-cycle-" + stable_loop_fingerprint(
                    {"loop_id": loop_id, "cycle_index": cycle_index, "step": step}
                )[:16],
                loop_id=loop_id,
                cycle_index=cycle_index,
                task_id=str(context.get("task", {}).get("task_id") or ""),
                execution_id=str(context.get("execution_id") or ""),
                status=status,
                step=copy.deepcopy(step),
                result=copy.deepcopy(result),
            )
            updated = RuntimeNativeAgentLoopRecord.from_dict(
                {
                    **loop.to_dict(),
                    "cycles": [item.to_dict() for item in loop.cycles] + [cycle.to_dict()],
                    "updated_at": utc_timestamp(),
                }
            )
            self._loops[loop_id] = updated
            self._append_event(
                LOOP_EVENT_STEP_EXECUTED,
                loop_id=loop_id,
                task_id=cycle.task_id,
                execution_id=cycle.execution_id,
                payload={"cycle": cycle.to_dict()},
            )
            self.save()
            return result
        return runner

    def _heartbeat(self, config: RuntimeNativeAgentLoopConfig, *, current_tick: int) -> None:
        if self.supervisor_bridge is None or not hasattr(self.supervisor_bridge, "heartbeat"):
            return
        if not config.source_session_id or not config.owner_id:
            return
        try:
            self.supervisor_bridge.heartbeat(
                config.source_session_id,
                config.owner_id,
                task_id=config.task_id,
                current_tick=current_tick,
            )
        except Exception:
            pass

    def _replace_loop(self, loop: RuntimeNativeAgentLoopRecord, **updates: Any) -> RuntimeNativeAgentLoopRecord:
        # Always start from the latest persisted loop to avoid overwriting
        # cycles appended by _cycle_runner while AER integration is executing.
        latest = self._loops.get(loop.loop_id, loop)
        payload = latest.to_dict()
        payload.update(copy.deepcopy(updates))
        payload["updated_at"] = utc_timestamp()
        updated = RuntimeNativeAgentLoopRecord.from_dict(payload)
        self._loops[updated.loop_id] = updated
        self.save()
        return copy.deepcopy(updated)

    def _append_event(
        self,
        event_type: str,
        *,
        loop_id: str = "",
        task_id: str = "",
        execution_id: str = "",
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        event_id = "runtime-native-loop-event-" + stable_loop_fingerprint(
            {
                "event_type": event_type,
                "loop_id": loop_id,
                "task_id": task_id,
                "execution_id": execution_id,
                "sequence": len(self._events) + 1,
            }
        )[:16]
        event = RuntimeNativeAgentLoopEvent(
            event_id=event_id,
            event_type=event_type,
            loop_id=str(loop_id or ""),
            task_id=str(task_id or ""),
            execution_id=str(execution_id or ""),
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
                    target.append_record("runtime_native_agent_loop", event.to_dict())
            except Exception:
                pass

    def _validate_text(self, field_name: str, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise RuntimeNativeAgentLoopRejected(f"{field_name}_required")
        return text
