from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


AER_INTEGRATION_STATUS_READY = "ready"
AER_INTEGRATION_STATUS_RUNNING = "running"
AER_INTEGRATION_STATUS_COMPLETED = "completed"
AER_INTEGRATION_STATUS_FAILED = "failed"
AER_INTEGRATION_STATUS_RECOVERED = "recovered"
AER_INTEGRATION_STATUS_BLOCKED = "blocked"

AER_COMPONENT_PLANNER = "planner"
AER_COMPONENT_SCHEDULER = "scheduler"
AER_COMPONENT_STEP_EXECUTOR = "step_executor"
AER_COMPONENT_AGENT_LOOP = "agent_loop"
AER_COMPONENT_MUTATION_RUNTIME = "mutation_runtime"

AER_EVENT_TASK_ACCEPTED = "aer_task_accepted"
AER_EVENT_PLAN_CREATED = "aer_plan_created"
AER_EVENT_EXECUTION_STARTED = "aer_execution_started"
AER_EVENT_STEP_EXECUTED = "aer_step_executed"
AER_EVENT_FAILURE_DETECTED = "aer_failure_detected"
AER_EVENT_RECOVERY_QUEUED = "aer_recovery_queued"
AER_EVENT_CONTINUATION_CREATED = "aer_continuation_created"
AER_EVENT_TASK_COMPLETED = "aer_task_completed"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_aer_fingerprint(value: Any) -> str:
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
class AERRuntimeComponentRef:
    component_id: str
    component_type: str
    status: str = AER_INTEGRATION_STATUS_READY
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "component_type": self.component_type,
            "status": self.status,
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AERRuntimeComponentRef":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            component_id=str(data.get("component_id") or ""),
            component_type=str(data.get("component_type") or ""),
            status=str(data.get("status") or AER_INTEGRATION_STATUS_READY),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class AERRuntimeTask:
    task_id: str
    goal: str
    source_session_id: str
    runtime_id: str = ""
    status: str = AER_INTEGRATION_STATUS_READY
    plan: dict[str, Any] = field(default_factory=dict)
    steps: list[dict[str, Any]] = field(default_factory=list)
    execution_id: str = ""
    transaction_id: str = ""
    continuation_ref: dict[str, Any] = field(default_factory=dict)
    recovery_ref: dict[str, Any] = field(default_factory=dict)
    final_result: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "source_session_id": self.source_session_id,
            "runtime_id": self.runtime_id,
            "status": self.status,
            "plan": copy.deepcopy(self.plan),
            "steps": copy.deepcopy(self.steps),
            "execution_id": self.execution_id,
            "transaction_id": self.transaction_id,
            "continuation_ref": copy.deepcopy(self.continuation_ref),
            "recovery_ref": copy.deepcopy(self.recovery_ref),
            "final_result": copy.deepcopy(self.final_result),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AERRuntimeTask":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            task_id=str(data.get("task_id") or ""),
            goal=str(data.get("goal") or ""),
            source_session_id=str(data.get("source_session_id") or ""),
            runtime_id=str(data.get("runtime_id") or ""),
            status=str(data.get("status") or AER_INTEGRATION_STATUS_READY),
            plan=_copy_dict(data.get("plan")),
            steps=_copy_list(data.get("steps")),
            execution_id=str(data.get("execution_id") or ""),
            transaction_id=str(data.get("transaction_id") or ""),
            continuation_ref=_copy_dict(data.get("continuation_ref")),
            recovery_ref=_copy_dict(data.get("recovery_ref")),
            final_result=_copy_dict(data.get("final_result")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class AERRuntimeIntegrationEvent:
    event_id: str
    event_type: str
    task_id: str = ""
    execution_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "task_id": self.task_id,
            "execution_id": self.execution_id,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "timestamp": self.timestamp,
            "source": "aer_runtime_integration",
        }


class AERRuntimeIntegrationRejected(RuntimeError):
    pass


PlannerFn = Callable[[str, dict[str, Any]], dict[str, Any]]
StepRunnerFn = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


class AERRuntimeIntegration:
    """
    Integration adapter that connects ZERO's planner/scheduler/executor mainline
    to the sealed Persistent Governed Runtime Core.

    It intentionally avoids editing Scheduler, StepExecutor, or agent_loop.

    Canonical integration flow:
        accept task
          -> planner adapter creates steps
          -> ownership authorize
          -> execution fabric start
          -> step runner executes under checkpointing
          -> failure queues recovery
          -> recovery builds continuation
          -> resume remaining execution
          -> complete task
    """

    def __init__(
        self,
        *,
        storage_path: str | Path | None = None,
        planner: Any = None,
        scheduler: Any = None,
        step_executor: Any = None,
        agent_loop: Any = None,
        mutation_runtime: Any = None,
        recovery_orchestrator: Any = None,
        execution_fabric: Any = None,
        transaction_fabric: Any = None,
        ownership_fabric: Any = None,
        supervisor_bridge: Any = None,
        journal: Any = None,
        audit: Any = None,
    ) -> None:
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self.planner = planner
        self.scheduler = scheduler
        self.step_executor = step_executor
        self.agent_loop = agent_loop
        self.mutation_runtime = mutation_runtime
        self.recovery_orchestrator = recovery_orchestrator
        self.execution_fabric = execution_fabric
        self.transaction_fabric = transaction_fabric
        self.ownership_fabric = ownership_fabric
        self.supervisor_bridge = supervisor_bridge
        self.journal = journal
        self.audit = audit
        self._components: dict[str, AERRuntimeComponentRef] = {}
        self._tasks: dict[str, AERRuntimeTask] = {}
        self._task_order: list[str] = []
        self._events: list[AERRuntimeIntegrationEvent] = []
        if self.storage_path is not None:
            self.load()

    @classmethod
    def with_workspace(
        cls,
        workspace_root: str | Path = "workspace",
        **kwargs: Any,
    ) -> "AERRuntimeIntegration":
        root = Path(workspace_root)
        integration_dir = root / "aer_runtime_integration"
        integration_dir.mkdir(parents=True, exist_ok=True)
        return cls(storage_path=integration_dir / "aer_runtime_integration.json", **kwargs)

    def register_component(
        self,
        component_type: str,
        *,
        component_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AERRuntimeComponentRef:
        component_type = self._validate_text("component_type", component_type)
        if component_id is None:
            component_id = "aer-component-" + stable_aer_fingerprint(
                {"component_type": component_type, "metadata": metadata or {}}
            )[:16]
        component_id = self._validate_text("component_id", component_id)

        ref = AERRuntimeComponentRef(
            component_id=component_id,
            component_type=component_type,
            metadata=copy.deepcopy(metadata or {}),
        )
        self._components[component_id] = ref
        self._append_event(
            "aer_component_registered",
            payload={"component": ref.to_dict()},
        )
        self.save()
        return copy.deepcopy(ref)

    def accept_task(
        self,
        *,
        goal: str,
        source_session_id: str,
        runtime_id: str = "",
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AERRuntimeTask:
        goal = self._validate_text("goal", goal)
        source_session_id = self._validate_text("source_session_id", source_session_id)
        if task_id is None:
            task_id = "aer-task-" + stable_aer_fingerprint(
                {
                    "goal": goal,
                    "source_session_id": source_session_id,
                    "runtime_id": runtime_id,
                }
            )[:16]
        task_id = self._validate_text("task_id", task_id)

        if task_id in self._tasks:
            raise AERRuntimeIntegrationRejected(f"aer task already exists: {task_id!r}")

        task = AERRuntimeTask(
            task_id=task_id,
            goal=goal,
            source_session_id=source_session_id,
            runtime_id=str(runtime_id or ""),
            metadata=copy.deepcopy(metadata or {}),
        )
        self._tasks[task_id] = task
        self._task_order.append(task_id)
        self._append_event(
            AER_EVENT_TASK_ACCEPTED,
            task_id=task_id,
            payload={"task": task.to_dict()},
        )
        self.save()
        return copy.deepcopy(task)

    def plan_task(
        self,
        task_id: str,
        *,
        planner_fn: PlannerFn | None = None,
        context: dict[str, Any] | None = None,
    ) -> AERRuntimeTask:
        task = self.get_task(task_id)
        plan = self._call_planner(task, planner_fn=planner_fn, context=context)
        steps = self._extract_steps(plan)

        updated = AERRuntimeTask.from_dict(
            {
                **task.to_dict(),
                "status": AER_INTEGRATION_STATUS_READY,
                "plan": plan,
                "steps": steps,
                "updated_at": utc_timestamp(),
            }
        )
        self._tasks[task_id] = updated
        self._append_event(
            AER_EVENT_PLAN_CREATED,
            task_id=task_id,
            payload={"task": updated.to_dict(), "plan": plan},
        )
        self.save()
        return copy.deepcopy(updated)

    def start_execution(self, task_id: str) -> AERRuntimeTask:
        task = self.get_task(task_id)
        if self.execution_fabric is None or not hasattr(self.execution_fabric, "start_execution"):
            raise AERRuntimeIntegrationRejected("execution_fabric_required")

        self._authorize_task_execution(task)

        execution = self.execution_fabric.start_execution(
            source_session_id=task.source_session_id,
            task_id=task.task_id,
            steps=copy.deepcopy(task.steps),
            payload={"goal": task.goal, "plan": task.plan},
            metadata={"runtime_id": task.runtime_id},
        )
        execution_id = str(getattr(execution, "execution_id", "") or "")
        updated = AERRuntimeTask.from_dict(
            {
                **task.to_dict(),
                "status": AER_INTEGRATION_STATUS_RUNNING,
                "execution_id": execution_id,
                "updated_at": utc_timestamp(),
            }
        )
        self._tasks[task_id] = updated
        self._append_event(
            AER_EVENT_EXECUTION_STARTED,
            task_id=task_id,
            execution_id=execution_id,
            payload={"task": updated.to_dict(), "execution": execution.to_dict() if hasattr(execution, "to_dict") else copy.deepcopy(execution)},
        )
        self.save()
        return copy.deepcopy(updated)

    def run_task(
        self,
        task_id: str,
        *,
        step_runner: StepRunnerFn | None = None,
        stop_on_failure: bool = True,
    ) -> AERRuntimeTask:
        task = self.get_task(task_id)
        if not task.execution_id:
            task = self.start_execution(task_id)

        failed = False
        failure_result: dict[str, Any] = {}

        for index, step in enumerate(task.steps, start=1):
            result = self._execute_step(
                task=task,
                step=step,
                step_index=index,
                step_runner=step_runner,
            )
            self.execution_fabric.record_step_result(
                task.execution_id,
                step_index=index,
                step=step,
                result=result,
                state_snapshot={
                    "task_id": task.task_id,
                    "step_index": index,
                    "steps_total": len(task.steps),
                },
            )
            self._append_event(
                AER_EVENT_STEP_EXECUTED,
                task_id=task.task_id,
                execution_id=task.execution_id,
                payload={"step": copy.deepcopy(step), "result": copy.deepcopy(result), "step_index": index},
            )
            if bool(result.get("failed", False)) or not bool(result.get("ok", True)):
                failed = True
                failure_result = result
                if stop_on_failure:
                    break

        if failed:
            updated = AERRuntimeTask.from_dict(
                {
                    **task.to_dict(),
                    "status": AER_INTEGRATION_STATUS_FAILED,
                    "final_result": copy.deepcopy(failure_result),
                    "updated_at": utc_timestamp(),
                }
            )
            self._tasks[task_id] = updated
            self._append_event(
                AER_EVENT_FAILURE_DETECTED,
                task_id=task.task_id,
                execution_id=task.execution_id,
                payload={"task": updated.to_dict(), "failure": failure_result},
            )
            self.save()
            return copy.deepcopy(updated)

        completed_execution = self.execution_fabric.complete_execution(
            task.execution_id,
            result={"ok": True, "status": "completed", "task_id": task.task_id},
        )
        updated = AERRuntimeTask.from_dict(
            {
                **task.to_dict(),
                "status": AER_INTEGRATION_STATUS_COMPLETED,
                "final_result": {"ok": True, "status": "completed", "execution_id": task.execution_id},
                "updated_at": utc_timestamp(),
            }
        )
        self._tasks[task_id] = updated
        self._append_event(
            AER_EVENT_TASK_COMPLETED,
            task_id=task.task_id,
            execution_id=task.execution_id,
            payload={"task": updated.to_dict(), "execution": completed_execution.to_dict() if hasattr(completed_execution, "to_dict") else copy.deepcopy(completed_execution)},
        )
        self.save()
        return copy.deepcopy(updated)

    def recover_task(
        self,
        task_id: str,
        *,
        current_tick: int = 0,
        reason: str = "",
    ) -> AERRuntimeTask:
        task = self.get_task(task_id)
        if not task.execution_id:
            raise AERRuntimeIntegrationRejected("task_has_no_execution_id")

        queued = self.execution_fabric.queue_recovery(
            task.execution_id,
            current_tick=current_tick,
            reason=reason or "aer task recovery requested",
        )
        continuation = self.execution_fabric.consume_recovery_and_build_continuation(
            task.execution_id,
            current_tick=current_tick,
        )

        updated = AERRuntimeTask.from_dict(
            {
                **task.to_dict(),
                "status": AER_INTEGRATION_STATUS_RECOVERED,
                "continuation_ref": continuation.to_dict() if hasattr(continuation, "to_dict") else copy.deepcopy(continuation),
                "recovery_ref": {
                    "queued_execution_status": getattr(queued, "status", ""),
                    "recovery_ticket": copy.deepcopy(getattr(queued, "recovery_ticket", {})),
                },
                "updated_at": utc_timestamp(),
            }
        )
        self._tasks[task_id] = updated
        self._append_event(
            AER_EVENT_RECOVERY_QUEUED,
            task_id=task.task_id,
            execution_id=task.execution_id,
            payload={"task": updated.to_dict(), "queued": queued.to_dict() if hasattr(queued, "to_dict") else copy.deepcopy(queued)},
        )
        self._append_event(
            AER_EVENT_CONTINUATION_CREATED,
            task_id=task.task_id,
            execution_id=task.execution_id,
            payload={"continuation": updated.continuation_ref},
        )
        self.save()
        return copy.deepcopy(updated)

    def resume_task(
        self,
        task_id: str,
        *,
        step_runner: StepRunnerFn | None = None,
    ) -> AERRuntimeTask:
        task = self.get_task(task_id)
        continuation_id = str(task.continuation_ref.get("continuation_id") or "")
        if not continuation_id:
            raise AERRuntimeIntegrationRejected("task_has_no_continuation_ref")

        completed = self.execution_fabric.resume_from_continuation(
            continuation_id,
            runner=step_runner,
        )
        updated = AERRuntimeTask.from_dict(
            {
                **task.to_dict(),
                "status": AER_INTEGRATION_STATUS_COMPLETED if getattr(completed, "status", "") == "completed" else AER_INTEGRATION_STATUS_RUNNING,
                "final_result": {
                    "ok": getattr(completed, "status", "") == "completed",
                    "execution_id": task.execution_id,
                    "execution_status": getattr(completed, "status", ""),
                },
                "updated_at": utc_timestamp(),
            }
        )
        self._tasks[task_id] = updated
        self._append_event(
            AER_EVENT_TASK_COMPLETED,
            task_id=task.task_id,
            execution_id=task.execution_id,
            payload={"task": updated.to_dict(), "execution": completed.to_dict() if hasattr(completed, "to_dict") else copy.deepcopy(completed)},
        )
        self.save()
        return copy.deepcopy(updated)

    def run_recover_resume(
        self,
        *,
        goal: str,
        source_session_id: str,
        runtime_id: str = "",
        planner_fn: PlannerFn | None = None,
        step_runner: StepRunnerFn | None = None,
        resume_runner: StepRunnerFn | None = None,
        current_tick: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> AERRuntimeTask:
        task = self.accept_task(
            goal=goal,
            source_session_id=source_session_id,
            runtime_id=runtime_id,
            metadata=metadata,
        )
        task = self.plan_task(task.task_id, planner_fn=planner_fn)
        task = self.start_execution(task.task_id)
        task = self.run_task(task.task_id, step_runner=step_runner)
        if task.status == AER_INTEGRATION_STATUS_FAILED:
            task = self.recover_task(
                task.task_id,
                current_tick=current_tick,
                reason="aer integration automatic recovery",
            )
            task = self.resume_task(
                task.task_id,
                step_runner=resume_runner or step_runner,
            )
        return task

    def get_task(self, task_id: str) -> AERRuntimeTask:
        task_id = self._validate_text("task_id", task_id)
        task = self._tasks.get(task_id)
        if task is None:
            raise AERRuntimeIntegrationRejected(f"aer task does not exist: {task_id!r}")
        return copy.deepcopy(task)

    def list_tasks(self) -> list[AERRuntimeTask]:
        return [
            copy.deepcopy(self._tasks[task_id])
            for task_id in self._task_order
            if task_id in self._tasks
        ]

    def list_events(self) -> list[AERRuntimeIntegrationEvent]:
        return [copy.deepcopy(event) for event in self._events]

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_phase": "aer_runtime_integration",
            "components": [component.to_dict() for component in self._components.values()],
            "tasks": [
                self._tasks[task_id].to_dict()
                for task_id in self._task_order
                if task_id in self._tasks
            ],
            "events": [event.to_dict() for event in self._events[-500:]],
        }

    def load(self) -> None:
        if self.storage_path is None:
            return
        if not self.storage_path.exists():
            self._components = {}
            self._tasks = {}
            self._task_order = []
            self._events = []
            return

        payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        self._components = {}
        self._tasks = {}
        self._task_order = []
        self._events = []
        if not isinstance(payload, dict):
            return

        for item in payload.get("components") or []:
            if isinstance(item, dict):
                component = AERRuntimeComponentRef.from_dict(item)
                if component.component_id:
                    self._components[component.component_id] = component

        for item in payload.get("tasks") or []:
            if isinstance(item, dict):
                task = AERRuntimeTask.from_dict(item)
                if task.task_id:
                    self._tasks[task.task_id] = task
                    self._task_order.append(task.task_id)

        for item in payload.get("events") or []:
            if isinstance(item, dict):
                event = AERRuntimeIntegrationEvent(
                    event_id=str(item.get("event_id") or ""),
                    event_type=str(item.get("event_type") or ""),
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
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _call_planner(
        self,
        task: AERRuntimeTask,
        *,
        planner_fn: PlannerFn | None,
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        context_payload = copy.deepcopy(context or {})
        context_payload["task"] = task.to_dict()

        if planner_fn is not None:
            result = planner_fn(task.goal, context_payload)
            return result if isinstance(result, dict) else {"steps": [], "raw_result": copy.deepcopy(result)}

        if self.planner is not None:
            for method_name in ("plan", "create_plan", "build_plan"):
                method = getattr(self.planner, method_name, None)
                if callable(method):
                    result = method(task.goal)
                    return result if isinstance(result, dict) else {"steps": [], "raw_result": copy.deepcopy(result)}

        return {
            "summary": "default AER integration plan",
            "steps": [
                {
                    "type": "respond",
                    "message": task.goal,
                }
            ],
        }

    def _extract_steps(self, plan: dict[str, Any]) -> list[dict[str, Any]]:
        steps = plan.get("steps") if isinstance(plan, dict) else []
        if not isinstance(steps, list):
            return []
        normalized = []
        for item in steps:
            if isinstance(item, dict):
                normalized.append(copy.deepcopy(item))
            else:
                normalized.append({"type": "value", "value": copy.deepcopy(item)})
        return normalized

    def _execute_step(
        self,
        *,
        task: AERRuntimeTask,
        step: dict[str, Any],
        step_index: int,
        step_runner: StepRunnerFn | None,
    ) -> dict[str, Any]:
        context = {
            "task": task.to_dict(),
            "step_index": step_index,
            "execution_id": task.execution_id,
        }

        if step_runner is not None:
            result = step_runner(copy.deepcopy(step), copy.deepcopy(context))
            return result if isinstance(result, dict) else {"ok": True, "result": copy.deepcopy(result)}

        if self.step_executor is not None:
            for method_name in ("execute_step", "execute", "run_step"):
                method = getattr(self.step_executor, method_name, None)
                if callable(method):
                    result = method(copy.deepcopy(step), context=copy.deepcopy(context))
                    return result if isinstance(result, dict) else {"ok": True, "result": copy.deepcopy(result)}

        return {"ok": True, "status": "completed", "step": copy.deepcopy(step)}

    def _authorize_task_execution(self, task: AERRuntimeTask) -> None:
        if self.ownership_fabric is None or not task.runtime_id:
            return
        if not hasattr(self.ownership_fabric, "authorize"):
            return
        decision = self.ownership_fabric.authorize(
            runtime_id=task.runtime_id,
            capability="execute",
            target=f"aer://task/{task.task_id}",
            owner_id=str(task.metadata.get("owner_id") or task.source_session_id),
        )
        decision_payload = decision.to_dict() if hasattr(decision, "to_dict") else copy.deepcopy(decision)
        if str(decision_payload.get("decision") or "") != "allow":
            raise AERRuntimeIntegrationRejected(
                "aer_runtime_execution_authority_denied: "
                f"{decision_payload.get('reason') or decision_payload}"
            )

    def _append_event(
        self,
        event_type: str,
        *,
        task_id: str = "",
        execution_id: str = "",
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        event_id = "aer-runtime-event-" + stable_aer_fingerprint(
            {
                "event_type": event_type,
                "task_id": task_id,
                "execution_id": execution_id,
                "sequence": len(self._events) + 1,
            }
        )[:16]
        event = AERRuntimeIntegrationEvent(
            event_id=event_id,
            event_type=event_type,
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
                    target.append_record("aer_runtime_integration", event.to_dict())
            except Exception:
                pass

    def _validate_text(self, field_name: str, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise AERRuntimeIntegrationRejected(f"{field_name}_required")
        return text
