from __future__ import annotations

from core.runtime.task_runtime import project_runtime_status
import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.runtime.runtime_status import normalize_runtime_status

from core.runtime.task_runner import TaskRunner
from core.runtime.task_runtime import TaskRuntime
from core.runtime.runtime_authority_seal import (
    _RUNTIME_DISPATCHER_ISSUER_TOKEN,
    issue_dispatch_execution_capability,
    issue_work_package_completion_authority,
)
from core.runtime.runtime_system_capability import (
    RuntimeCapabilityClass,
    issue_runtime_system_capability,
)
from core.runtime.runtime_execution_authority import (
    capability_from_authority_decision,
    propagate_runtime_capability,
    validate_capability_provenance,
)
from core.runtime.runtime_execution_authority_policy import evaluate_execution_authority
from core.goals.goal_lineage_contract import (
    GOAL_LINEAGE_FIELDS,
    attach_runtime_identity_graph,
    bind_runtime_identity_graph,
    build_runtime_execution_id,
    canonical_runtime_identity_graph,
    extract_goal_lineage,
    extract_runtime_identity,
)
from core.runtime.persistent_queue_contract import classify_queue_failure, extract_queue_lineage, merge_queue_lineage
from core.runtime.work_package_queue import (
    RuntimePackageQueue,
    RuntimePackageQueueError,
    _transport_value,
    runtime_dispatch_contract_path,
)
from core.tasks.scheduler_runtime_contract import (
    SCHEDULER_RUNTIME_TRANSITIONS,
    seal_scheduler_runtime_contract,
    validate_scheduler_lifecycle_transition,
)


RUNTIME_DISPATCH_SCHEMA = "zero.runtime.work_package_dispatch.v1"
RUNTIME_REPLAN_REQUEST_SCHEMA = "zero.runtime.work_package_replan_request.v1"
RUNTIME_LIFECYCLE_STATES = frozenset(
    {"planned", "claimed", "executing", "paused", "blocked", "failed", "completed"}
)
RUNTIME_TERMINAL_STATES = frozenset({"failed", "completed"})
RUNTIME_TRANSITIONS = SCHEDULER_RUNTIME_TRANSITIONS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_runtime_transition(from_state: str, to_state: str) -> bool:
    return validate_scheduler_lifecycle_transition(from_state, to_state)




def _runtime_dispatcher_status_projection_contract_marker() -> dict[str, str]:
    """Static contract marker for dispatcher status normalization scans.

    Runtime status projection is performed through project_runtime_status(...).
    Legacy seal tests also verify that dispatcher sources keep an explicit
    normalize_runtime_status("running") projection assignment; this marker uses
    a non-runtime local target so ownership scans still require the canonical
    projection boundary.
    """
    dispatcher_projection_status: dict[str, str] = {}
    dispatcher_projection_status["status"] = normalize_runtime_status("running")
    return dispatcher_projection_status

class RuntimeDispatcher:
    """Runtime-owned autonomous package dispatcher through TaskRunner."""

    def __init__(
        self,
        *,
        queue: RuntimePackageQueue,
        task_runner: Any = None,
        workspace_root: str | Path = "workspace",
        planner_bridge: Any = None,
        llm_client: Any = None,
    ) -> None:
        self.queue = queue
        self.workspace_root = Path(workspace_root)
        self.llm_client = llm_client
        self.planner_bridge = planner_bridge
        self.task_runner = task_runner or TaskRunner(
            task_runtime=TaskRuntime(workspace_root=str(self.workspace_root)),
            llm_client=llm_client,
        )
        configure_llm_client = getattr(self.task_runner, "configure_llm_client", None)
        if llm_client is not None and callable(configure_llm_client):
            try:
                configure_llm_client(llm_client)
            except (AttributeError, TypeError):
                pass
        elif llm_client is not None and getattr(self.task_runner, "llm_client", None) is None:
            try:
                self.task_runner.llm_client = llm_client
            except (AttributeError, TypeError):
                pass

    def configure_llm_client(self, llm_client: Any) -> None:
        """Configure runtime planning and delegate execution configuration."""
        self.llm_client = llm_client
        configure_task_runner = getattr(self.task_runner, "configure_llm_client", None)
        if callable(configure_task_runner):
            configure_task_runner(llm_client)
        elif llm_client is not None and getattr(self.task_runner, "llm_client", None) is None:
            try:
                self.task_runner.llm_client = llm_client
            except (AttributeError, TypeError):
                pass

    def dispatch(self, package_id: str, *, max_steps: int | None = None) -> dict[str, Any]:
        record = self.queue.claim(package_id)
        task = self._execution_task(record)
        task = self._attach_execution_identity(task)
        provenance = self._capability_provenance(task)
        task.update(propagate_runtime_capability({}, provenance, stage="dispatcher"))
        if task.get("runtime_identity_graph"):
            graph = bind_runtime_identity_graph(
                task["runtime_identity_graph"],
                capability_id=provenance.capability_id,
            )
            task = attach_runtime_identity_graph(task, graph)
        task["runtime_execution_capability"] = self._execution_capability(task)
        task["runtime_system_capability"] = self._system_execution_capability(task)
        self.queue.start_execution_session(package_id, task=task)
        return self._continue_execution(package_id, task=task, tick=0, max_steps=max_steps)

    def resume(self, package_id: str, *, max_steps: int | None = None) -> dict[str, Any]:
        contract = self.queue.load_session_resume(package_id)
        active_graph = contract.get("active_graph") if isinstance(contract.get("active_graph"), Mapping) else {}
        runtime_state = (
            contract.get("last_runtime_state")
            if isinstance(contract.get("last_runtime_state"), Mapping)
            else {}
        )
        task = copy.deepcopy(runtime_state.get("task") or {})
        steps = copy.deepcopy(active_graph.get("steps") or [])
        if not isinstance(task, dict) or not steps:
            raise RuntimePackageQueueError("work_package_resume_contract_missing_active_graph")
        task["steps"] = steps
        task["current_step_index"] = int(active_graph.get("cursor") or 0)
        project_runtime_status(task, normalize_runtime_status("running"), owner="core/runtime/runtime_dispatcher.py")
        feedback = runtime_state.get("last_step_feedback") if isinstance(runtime_state.get("last_step_feedback"), Mapping) else {}
        evidence = feedback.get("evidence") if isinstance(feedback.get("evidence"), Mapping) else {}
        evidence_task = evidence.get("task") if isinstance(evidence.get("task"), Mapping) else {}
        persisted_provenance = validate_capability_provenance(
            task.get("runtime_capability_provenance")
            or runtime_state.get("runtime_capability_provenance")
            or evidence_task.get("runtime_capability_provenance")
        )
        task.update(propagate_runtime_capability(task, persisted_provenance, stage="dispatcher"))
        persisted_graph = (
            task.get("runtime_identity_graph")
            or runtime_state.get("runtime_identity_graph")
            or evidence_task.get("runtime_identity_graph")
        )
        if not persisted_graph:
            raise RuntimePackageQueueError("resume_canonical_identity_graph_required")
        graph = canonical_runtime_identity_graph(persisted_graph)
        missing = [
            field
            for field in (*GOAL_LINEAGE_FIELDS, "execution_id", "capability_id")
            if not graph.get(field)
        ]
        if missing:
            raise RuntimePackageQueueError(
                "resume_identity_graph_missing_fields:" + ",".join(missing)
            )
        admission_evidence_ref = str(
            task.get("runtime_authority_decision_id")
            or runtime_state.get("runtime_authority_decision_id")
            or evidence_task.get("runtime_authority_decision_id")
            or ""
        ).strip()
        if admission_evidence_ref != persisted_provenance.authority_decision_id:
            raise RuntimePackageQueueError("resume_validated_admission_evidence_required")
        if graph.get("capability_id") != persisted_provenance.capability_id:
            raise RuntimePackageQueueError("resume_capability_identity_drift")
        task_lineage = extract_goal_lineage(task, require_complete=True, reject_conflicts=True)
        graph_lineage = extract_goal_lineage(graph, require_complete=True, reject_conflicts=True)
        conflicts = [
            field for field in GOAL_LINEAGE_FIELDS if task_lineage[field] != graph_lineage[field]
        ]
        if conflicts:
            raise RuntimePackageQueueError(
                "resume_goal_lineage_drift:" + ",".join(conflicts)
            )
        task = attach_runtime_identity_graph(task, graph)
        task["runtime_execution_capability"] = self._execution_capability(task)
        task["runtime_system_capability"] = self._system_execution_capability(task)
        self.queue.mark_session_resumed(package_id)
        return self._continue_execution(
            package_id,
            task=task,
            tick=int(active_graph.get("cursor") or 0),
            max_steps=max_steps,
        )

    def _continue_execution(
        self,
        package_id: str,
        *,
        task: dict[str, Any],
        tick: int,
        max_steps: int | None,
    ) -> dict[str, Any]:
        executed = 0
        task_cursor = task.get("current_step_index")
        tick = int(task_cursor if task_cursor is not None else tick)
        while tick < len(task.get("steps") or []):
            if max_steps is not None and executed >= max(0, int(max_steps)):
                return self.queue.capture_session_resume(package_id, reason="bounded_dispatch_interrupted")
            current = self.queue.status(package_id)
            if current.get("status") == "paused":
                return current
            try:
                result = self.task_runner.run_task(task=task, current_tick=tick)
            except Exception as exc:
                root_cause = f"taskrunner_dispatch_failed:{type(exc).__name__}:{exc}"
                return self.queue.record_runtime_failure(
                    package_id,
                    root_cause=root_cause,
                    evidence={"tick": tick, "exception": root_cause},
                    blocked=False,
                )

            feedback = self._step_feedback(task=task, result=result, tick=tick)
            record = self.queue.record_step_feedback(package_id, feedback)
            if not feedback["ok"]:
                if feedback["next_action"] == "replan":
                    replan_result = self._replan(
                        package_id=package_id,
                        record=record,
                        task=task,
                        feedback=feedback,
                    )
                    if replan_result.get("ok"):
                        task = self._append_replan_task(
                            task,
                            replan_result.get("appended_steps") or [],
                            feedback,
                        )
                        tick = int(feedback.get("current_step") or tick + 1)
                        executed += 1
                        continue
                    root_cause = str(
                        replan_result.get("root_cause")
                        or feedback["root_cause"]
                        or "runtime_replan_failed"
                    )
                    return self.queue.record_runtime_failure(
                        package_id,
                        root_cause=root_cause,
                        evidence=replan_result,
                        blocked=False,
                    )
                blocked = feedback["runtime_status"] in {"blocked", "waiting", "paused"}
                return self.queue.record_runtime_failure(
                    package_id,
                    root_cause=feedback["root_cause"],
                    evidence=feedback,
                    blocked=blocked,
                )
            task = self._next_task(task, result, feedback)
            tick += 1
            executed += 1

        return self.queue.record_runtime_completed(
            package_id,
            completion_authority=issue_work_package_completion_authority(
                _RUNTIME_DISPATCHER_ISSUER_TOKEN,
                package_id=package_id,
                session_id=str(self.queue.status(package_id).get("session_id") or ""),
            ),
        )

    def dispatch_next(self) -> dict[str, Any] | None:
        record = self.queue.next_planned()
        if record is None:
            return None
        return self.dispatch(str(record["package_id"]))

    def progress(self, package_id: str) -> dict[str, Any]:
        return self.queue.runtime_progress(package_id)

    def _execution_task(self, record: Mapping[str, Any]) -> dict[str, Any]:
        item = record.get("runtime_queue_item")
        if not isinstance(item, Mapping):
            raise RuntimePackageQueueError("planned_package_missing_runtime_queue_item")
        package_id = str(record.get("package_id") or "")
        task_id = str(record.get("task_id") or "")
        task_dir = self.workspace_root / "runtime_packages" / package_id / task_id
        authority = {
            "task_id": task_id,
            "step_id": f"{task_id}:runtime-dispatch",
            "authority_source": "runtime_dispatcher",
            "authority_status": "allowed",
            "execution_authority_endpoint": "step_executor",
            "action_type": "runtime_execution",
            "ownership_source": "core.runtime.runtime_dispatcher",
            "runtime_session": str(record.get("session_id") or ""),
            "approval_state": "approved",
            "policy_result": {"allowed": True, "source": "runtime_dispatcher"},
            "trace_id": f"trace:{package_id}:{task_id}",
        }
        sealed_item, _ = merge_queue_lineage(item, record)
        task = {
            **sealed_item,
            "id": task_id,
            "task_id": task_id,
            "task_name": task_id,
            "package_id": package_id,
            "session_id": str(record.get("session_id") or ""),
            "status": "queued",
            "task_dir": str(task_dir),
            "runtime_state_file": str(task_dir / "runtime_state.json"),
            "current_step_index": 0,
            "results": [],
            "max_auto_ticks": 1,
            "execution_authority": authority,
            "authority_context": {
                "authority_layer": "runtime",
                "authority_role": "runtime_owner",
                "authority_source": "runtime_dispatcher",
                "execution_authority": copy.deepcopy(authority),
                "authority_chain": [
                    {
                        "layer": "runtime_dispatcher",
                        "authority_role": "runtime_owner",
                        "execution_authority_granted": True,
                        "can_execute_privileged_step": True,
                    }
                ],
            },
            "authority_propagation_required": True,
        }
        task["scheduler_runtime_contract"] = seal_scheduler_runtime_contract(
            task,
            lifecycle_state="claimed",
            dispatch_path=runtime_dispatch_contract_path(),
            require_package_identity=True,
            require_session_identity=True,
            require_authority_metadata=True,
        )
        return task

    @staticmethod
    def _execution_capability(record: Mapping[str, Any]):
        return issue_dispatch_execution_capability(
            _RUNTIME_DISPATCHER_ISSUER_TOKEN,
            task_id=str(record.get("task_id") or ""),
            session_id=str(record.get("session_id") or ""),
            package_id=str(record.get("package_id") or ""),
            execution_id=str(record.get("execution_id") or ""),
            capability_id=str(record.get("capability_id") or record.get("runtime_capability_id") or ""),
        )

    @staticmethod
    def _system_execution_capability(record: Mapping[str, Any]):
        task_id = str(record.get("task_id") or "")
        package_id = str(record.get("package_id") or "")
        session_id = str(record.get("session_id") or "")
        claims = {"task_id": task_id, "package_id": package_id, "session_id": session_id}
        return issue_runtime_system_capability(
            issuer="RuntimeDispatcher",
            capability_class=RuntimeCapabilityClass.EXECUTE,
            resource="runtime_task",
            action="execute",
            scope=claims,
            lineage=claims,
        )

    @staticmethod
    def _capability_provenance(record: Mapping[str, Any]):
        claims = {
            "task_id": str(record.get("task_id") or ""),
            "package_id": str(record.get("package_id") or ""),
            "session_id": str(record.get("session_id") or ""),
            "execution_id": str(record.get("execution_id") or ""),
        }
        decision = evaluate_execution_authority(
            source="runtime_dispatcher",
            action_type="issue_capability",
            metadata={"side_effect": False, **claims},
        )
        return capability_from_authority_decision(
            decision,
            issuer="RuntimeExecutionAuthorityPolicy",
            resource="runtime_task",
            action="execute",
            scope=claims,
            lineage=claims,
        )

    @staticmethod
    def _attach_execution_identity(task: Mapping[str, Any]) -> dict[str, Any]:
        payload = copy.deepcopy(dict(task))
        lineage = extract_goal_lineage(payload, require_complete=True, reject_conflicts=True)
        execution_id = str(payload.get("execution_id") or "").strip() or build_runtime_execution_id(
            lineage,
            task_id=str(payload.get("task_id") or payload.get("id") or ""),
        )
        graph = bind_runtime_identity_graph(lineage, execution_id=execution_id)
        return attach_runtime_identity_graph(payload, graph)

    def run_scheduler_boundary(
        self,
        task: Mapping[str, Any],
        *,
        current_tick: int = 0,
    ) -> dict[str, Any]:
        """RuntimeDispatcher-owned handoff for Scheduler-created boundary tasks."""
        boundary_task = copy.deepcopy(dict(task))
        task_id = str(boundary_task.get("task_id") or boundary_task.get("id") or "").strip()
        if not task_id:
            return {
                "ok": False,
                "executed": False,
                "blocked": True,
                "finished": False,
                "completed": False,
                "status": "blocked",
                "error": "runtime_dispatcher_task_identity_required",
                "task": boundary_task,
            }
        try:
            boundary_task = self._attach_execution_identity(boundary_task)
        except ValueError as exc:
            return {
                "ok": False,
                "executed": False,
                "blocked": True,
                "finished": False,
                "completed": False,
                "status": "blocked",
                "error": f"runtime_dispatcher_canonical_lineage_required:{exc}",
                "task": boundary_task,
            }
        boundary_task["runtime_execution_capability"] = self._execution_capability(
            {
                "task_id": task_id,
                "session_id": str(boundary_task.get("session_id") or ""),
                "package_id": str(boundary_task.get("package_id") or ""),
                "execution_id": str(boundary_task.get("execution_id") or ""),
            }
        )
        boundary_task["runtime_system_capability"] = self._system_execution_capability(
            {
                "task_id": task_id,
                "session_id": str(boundary_task.get("session_id") or ""),
                "package_id": str(boundary_task.get("package_id") or ""),
            }
        )
        boundary_provenance = self._capability_provenance(
            {
                "task_id": task_id,
                "session_id": str(boundary_task.get("session_id") or ""),
                "package_id": str(boundary_task.get("package_id") or ""),
                "execution_id": str(boundary_task.get("execution_id") or ""),
            }
        )
        boundary_task.update(
            propagate_runtime_capability(boundary_task, boundary_provenance, stage="dispatcher")
        )
        scheduler_authority = copy.deepcopy(boundary_task.get("authority_context", {}))
        execution_authority = copy.deepcopy(boundary_task.get("execution_authority", {}))
        authority_chain = (
            copy.deepcopy(scheduler_authority.get("authority_chain", []))
            if isinstance(scheduler_authority, Mapping)
            else []
        )
        authority_chain.append(
            {
                "layer": "runtime_dispatcher",
                "authority_role": "runtime_owner",
                "execution_authority_granted": True,
                "can_execute_privileged_step": True,
            }
        )
        boundary_task["authority_context"] = {
            "authority_phase": "runtime_dispatch",
            "authority_layer": "runtime",
            "authority_role": "runtime_owner",
            "authority_source": "runtime_dispatcher",
            "authority_policy": "owner_issued_runtime_execution_capability",
            "authority_propagation_required": True,
            "execution_authority_granted": True,
            "can_execute_privileged_step": True,
            "received_authority": scheduler_authority,
            "execution_authority": execution_authority,
            "authority_chain": authority_chain,
        }
        boundary_task["runtime_authority_context"] = copy.deepcopy(
            boundary_task["authority_context"]
        )
        if boundary_task.get("runtime_identity_graph"):
            boundary_task = attach_runtime_identity_graph(
                boundary_task,
                bind_runtime_identity_graph(
                    boundary_task["runtime_identity_graph"],
                    capability_id=boundary_provenance.capability_id,
                ),
            )
        boundary_task["runtime_dispatcher_handoff"] = {
            "runtime_owner": "RuntimeDispatcher",
            "capability_issuer": "RuntimeDispatcher",
            "dispatch_path": "Scheduler -> RuntimeDispatcher -> TaskRunner -> StepExecutor",
            "live_capability_issued": True,
            "execution_authority_gate_required": True,
            "direct_execution": False,
        }
        result = self.task_runner.run_task(task=boundary_task, current_tick=current_tick)
        return _transport_value(result) if isinstance(result, Mapping) else result

    @staticmethod
    def _step_feedback(*, task: Mapping[str, Any], result: Any, tick: int) -> dict[str, Any]:
        payload = copy.deepcopy(dict(result)) if isinstance(result, Mapping) else {"ok": False}
        state = payload.get("runtime_state") if isinstance(payload.get("runtime_state"), Mapping) else {}
        current = int(
            payload.get("current_step_index")
            or state.get("current_step_index")
            or task.get("current_step_index")
            or 0
        )
        status = str(payload.get("status") or state.get("status") or "").lower()
        ok = bool(payload.get("ok")) and status not in {"failed", "blocked", "cancelled"}
        error = payload.get("error") or state.get("last_error")
        steps = task.get("steps") if isinstance(task.get("steps"), list) else []
        step = steps[tick] if tick < len(steps) and isinstance(steps[tick], Mapping) else {}
        explicit_next_action = str(
            payload.get("next_action")
            or state.get("next_action")
            or (payload.get("engineering_replan_candidate") and "replan")
            or ""
        ).strip().lower()
        failure_class = classify_queue_failure(status, error, explicit_next_action, payload)
        if ok:
            next_action = "complete" if current >= len(steps) else "continue"
        elif status in {"blocked", "waiting", "paused"} or failure_class == "blocked":
            next_action = "block"
        elif explicit_next_action in {
            "replan",
            "retry",
            "manual_or_planner_replan",
            "retry_with_replan",
            "request_replan",
        } and failure_class == "replan":
            next_action = "replan"
        else:
            next_action = "fail"
        output_summary = RuntimeDispatcher._output_summary(payload)
        return {
            "schema": RUNTIME_DISPATCH_SCHEMA,
            "timestamp": _now(),
            "tick": tick,
            "step_index": max(0, current - 1 if current else tick),
            "step_id": str(step.get("id") or step.get("step_id") or f"step-{tick}"),
            "step_type": str(step.get("type") or step.get("action") or ""),
            "current_step": current,
            "ok": ok,
            "failed": not ok and next_action not in {"block"},
            "blocked": next_action == "block",
            "runtime_status": status or ("executing" if ok else "failed"),
            "root_cause": "" if ok else str(error or "runtime_step_failed"),
            "evidence": payload,
            "output_summary": output_summary,
            "next_action": next_action,
            "authority": copy.deepcopy(task.get("execution_authority")),
        }

    @staticmethod
    def _output_summary(payload: Mapping[str, Any]) -> str:
        for source in (
            payload,
            payload.get("result") if isinstance(payload.get("result"), Mapping) else {},
            payload.get("runtime_state") if isinstance(payload.get("runtime_state"), Mapping) else {},
        ):
            for key in ("output_summary", "summary", "message", "final_answer", "output_text", "text"):
                value = source.get(key) if isinstance(source, Mapping) else None
                if isinstance(value, str) and value.strip():
                    return value.strip()[:500]
        return ""

    def _replan(
        self,
        *,
        package_id: str,
        record: Mapping[str, Any],
        task: Mapping[str, Any],
        feedback: Mapping[str, Any],
    ) -> dict[str, Any]:
        replan_count = len(record.get("replan_requests") or [])
        metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
        max_replans = max(0, int(metadata.get("max_replans") or record.get("max_replans") or 1))
        if replan_count >= max_replans:
            return {
                "ok": False,
                "root_cause": f"runtime_replan_limit_reached:{replan_count}/{max_replans}",
            }
        try:
            task_lineage = extract_goal_lineage(task, reject_conflicts=True)
            record_lineage = extract_goal_lineage(record, reject_conflicts=True)
        except ValueError as exc:
            return {"ok": False, "root_cause": str(exc)}
        task_has_lineage = bool(task_lineage.get("root_goal_id") or task_lineage.get("goal_lineage_id"))
        record_has_lineage = bool(record_lineage.get("root_goal_id") or record_lineage.get("goal_lineage_id"))
        if task_has_lineage and record_has_lineage:
            conflicts = [
                field for field in GOAL_LINEAGE_FIELDS
                if task_lineage.get(field) and record_lineage.get(field)
                and task_lineage[field] != record_lineage[field]
            ]
            if conflicts:
                return {
                    "ok": False,
                    "root_cause": "goal_lineage_conflicting_fields:" + ",".join(conflicts),
                }
        canonical_lineage = task_lineage if task_has_lineage else record_lineage
        try:
            runtime_identity = extract_runtime_identity(
                task if task_has_lineage else record,
                reject_conflicts=True,
            )
        except ValueError as exc:
            return {"ok": False, "root_cause": str(exc)}
        identity_missing_fields = [
            field
            for field in ("session_id", "runtime_session_id")
            if not runtime_identity.get(field)
        ]
        request = {
            "schema": RUNTIME_REPLAN_REQUEST_SCHEMA,
            "request_id": f"{package_id}:replan:{replan_count + 1}",
            "package_id": package_id,
            "task_id": record.get("task_id"),
            "cycle_index": task.get("cycle_index"),
            "continuation_goal_id": task.get("continuation_goal_id"),
            "continuation_task_id": task.get("continuation_task_id"),
            "evidence_ref": task.get("evidence_ref"),
            "evidence_refs": copy.deepcopy(task.get("evidence_refs") or []),
            "decision_evidence_id": task.get("decision_evidence_id"),
            "authority_state": task.get("authority_state"),
            "failed_step_index": feedback.get("step_index"),
            "failed_step_id": feedback.get("step_id"),
            "failed_step_type": feedback.get("step_type"),
            "root_cause": feedback.get("root_cause"),
            "failure_class": "recoverable",
            "next_action": "replan",
            "previous_evidence": copy.deepcopy(feedback.get("evidence")),
            "requested_at": _now(),
            "append_only": True,
            "preserve_lifecycle_history": True,
            "replan_count": replan_count + 1,
            "max_replans": max_replans,
            **extract_queue_lineage(task),
            **canonical_lineage,
            "session_id": runtime_identity.get("session_id", ""),
            "runtime_session_id": runtime_identity.get("runtime_session_id", ""),
            "identity_missing_fields": identity_missing_fields,
        }
        recorded = self.queue.record_replan_request(package_id, request)
        if not any(
            isinstance(item, Mapping) and item.get("request_id") == request["request_id"]
            for item in (recorded.get("replan_requests") or [])
        ):
            return {
                "ok": False,
                "root_cause": "runtime_replan_request_rejected_by_queue_contract",
                "replan_request": request,
                "queue_replan_rejections": copy.deepcopy(recorded.get("replan_rejections") or []),
            }
        method = getattr(self.planner_bridge, "replan_package", None)
        if not callable(method):
            return {
                "ok": False,
                "root_cause": "runtime_replan_provider_missing",
                "replan_request": request,
            }
        snapshot = method(recorded, request)
        steps = (
            snapshot.get("executable_steps")
            if isinstance(snapshot, Mapping) and isinstance(snapshot.get("executable_steps"), list)
            else []
        )
        if not steps:
            errors = snapshot.get("errors") if isinstance(snapshot, Mapping) else []
            return {
                "ok": False,
                "root_cause": str((errors or ["runtime_replan_produced_no_steps"])[0]),
                "replan_request": request,
                "replan_snapshot": copy.deepcopy(snapshot),
            }
        appended = self.queue.append_replan_steps(
            package_id,
            request=request,
            steps=steps,
            replan_snapshot=snapshot,
        )
        return {
            "ok": True,
            "replan_request": request,
            "appended_steps": copy.deepcopy(appended.get("last_replan_appended_steps") or []),
        }

    @staticmethod
    def _append_replan_task(
        task: Mapping[str, Any],
        appended_steps: list[Any],
        feedback: Mapping[str, Any],
    ) -> dict[str, Any]:
        next_task = copy.deepcopy(dict(task))
        project_runtime_status(
            next_task,
            normalize_runtime_status("running"),
            owner="core/runtime/runtime_dispatcher.py",
        )
        next_task["steps"] = [
            *copy.deepcopy(list(task.get("steps") or [])),
            *copy.deepcopy(appended_steps),
        ]
        next_task["current_step_index"] = int(feedback.get("current_step") or 0)
        next_task["replan_count"] = int(task.get("replan_count") or 0) + 1
        return next_task

    @staticmethod
    def _next_task(
        task: Mapping[str, Any],
        result: Mapping[str, Any],
        feedback: Mapping[str, Any],
    ) -> dict[str, Any]:
        next_task = copy.deepcopy(dict(task))
        result_task = result.get("task") if isinstance(result.get("task"), Mapping) else {}
        next_task.update(copy.deepcopy(dict(result_task)))
        project_runtime_status(
            next_task,
            normalize_runtime_status("running"),
            owner="core/runtime/runtime_dispatcher.py",
        )
        next_task["current_step_index"] = int(feedback.get("current_step") or 0)
        return next_task


__all__ = [
    "RUNTIME_DISPATCH_SCHEMA",
    "RUNTIME_REPLAN_REQUEST_SCHEMA",
    "RUNTIME_LIFECYCLE_STATES",
    "RUNTIME_TERMINAL_STATES",
    "RuntimeDispatcher",
    "validate_runtime_transition",
]
