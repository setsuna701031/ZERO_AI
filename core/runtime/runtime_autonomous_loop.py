from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


RUNTIME_AUTONOMOUS_LOOP_SCHEMA = "zero.runtime.autonomous_loop.v1"
RUNTIME_AUTONOMOUS_MISSION_DRIVER_SCHEMA = "zero.runtime.autonomous_mission_driver.v1"

def project_runtime_session(session: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a read-only operator-session projection; never resumes a session."""
    value = _mapping(session)
    status, phase, action = value.get("session_status"), value.get("current_phase"), value.get("required_action")
    tx = _mapping(_mapping(value.get("artifacts")).get("transaction_result"))
    transaction_status = tx.get("transaction_status")
    waiting = isinstance(status, str) and status.startswith("waiting_for_")
    return {"runtime_session_present": bool(value), "session_status": status, "current_phase": phase,
        "required_action": action, "waiting_for_operator": waiting,
        "proposal_ready": phase == "proposal_ready", "plan_ready": phase == "execution_plan_ready",
        "controlled_dry_run_completed": phase == "controlled_dry_run_completed",
        "active_execution_prepared": phase == "active_execution_prepared",
        "candidate_bundle_ready": phase == "candidate_bundle_ready",
        "transaction_ready": action == "transactional_invocation", "transaction_status": transaction_status,
        "transaction_committed": transaction_status == "committed", "validation_passed": tx.get("validation_passed") is True,
        "rollback_executed": tx.get("rollback_executed") is True, "rollback_verified": tx.get("rollback_verified") is True,
        "critical_failure": status == "failed" and _mapping(value.get("failure")).get("critical") is True,
        "completed": value.get("completed") is True}

def project_runtime_scheduler(state: Mapping[str, Any] | None) -> dict[str, Any]:
    """Project scheduler state without leasing, dispatching, or mutating it."""
    value = _mapping(state); entries = list(value.get("entries") or []); waiting = list(value.get("waiting_operator_sessions") or [])
    try:
        from core.runtime.runtime_session_queue import ordered_entries, validate_scheduler_state
        from core.runtime.runtime_session_scheduler import compute_scheduler_stats
        valid = not validate_scheduler_state(value) if value else False
        stats = compute_scheduler_stats(value) if value else {}
        queued = [item for item in ordered_entries(value, include_terminal=False) if item.get("lease_status") != "active" and item.get("session_status") not in {"waiting_for_operator_approval", "waiting_for_plan_review", "waiting_for_active_authorization", "waiting_for_candidate_bundle", "waiting_for_transaction_invocation"}]
    except (TypeError, ValueError): valid, stats, queued = False, {}, []
    next_entry = queued[0] if queued else {}
    return {"scheduler_present": bool(value), "scheduler_status": value.get("scheduler_status"), "scheduler_state_valid": valid,
        "scheduler_queue_size": len(entries), "scheduler_leased_count": stats.get("leased", 0), "scheduler_waiting_count": stats.get("waiting_operator", 0),
        "scheduler_completed_count": stats.get("completed", 0), "scheduler_failed_count": stats.get("failed", 0),
        "scheduler_critical_count": stats.get("critical_failure", 0), "scheduler_expired_count": stats.get("expired", 0),
        "scheduler_cancelled_count": stats.get("cancelled", 0), "next_queued_session_id": next_entry.get("session_id"),
        "next_queued_priority": next_entry.get("priority"),
        "waiting_actions_summary": sorted({str(item.get("required_action")) for item in waiting if item.get("required_action")}),
        "active_leases_summary": [{"session_id": item.get("session_id"), "lease_id": item.get("lease_id"), "lease_owner": item.get("lease_owner"), "lease_expires_at": item.get("lease_expires_at")} for item in entries if item.get("lease_status") == "active"],
        "scheduler_sessions_total": stats.get("total_sessions", 0), "scheduler_sessions_queued": stats.get("queued", 0),
        "scheduler_sessions_leased": stats.get("leased", 0), "scheduler_sessions_waiting": stats.get("waiting_operator", 0),
        "scheduler_sessions_completed": stats.get("completed", 0), "scheduler_sessions_failed": stats.get("failed", 0),
        "scheduler_sessions_critical": stats.get("critical_failure", 0)}

def project_runtime_worker(state: Mapping[str, Any] | None, *, now: Any = None) -> dict[str, Any]:
    value = _mapping(state)
    try:
        from core.runtime.runtime_worker_service import worker_health
        health = worker_health(value, now=now) if value else {}
    except (TypeError, ValueError): health = {"healthy": False, "heartbeat_fresh": False}
    lease = _mapping(value.get("current_lease")); status = value.get("worker_status")
    return {"runtime_worker_present": bool(value), "runtime_worker_status": status, "runtime_worker_healthy": health.get("healthy") is True,
        "runtime_worker_heartbeat_fresh": health.get("heartbeat_fresh") is True, "runtime_worker_current_session_id": value.get("current_session_id"),
        "runtime_worker_current_lease_id": lease.get("lease_id"), "runtime_worker_loop_iteration": int(value.get("loop_iteration") or 0),
        "runtime_worker_successful_dispatches": int(value.get("successful_dispatches") or 0),
        "runtime_worker_waiting_dispatches": int(value.get("waiting_dispatches") or 0),
        "runtime_worker_blocked_dispatches": int(value.get("blocked_dispatches") or 0),
        "runtime_worker_failed_dispatches": int(value.get("failed_dispatches") or 0),
        "runtime_worker_critical_failures": int(value.get("critical_failures") or 0),
        "runtime_worker_stop_requested": value.get("stop_requested") is True, "runtime_worker_pause_requested": value.get("pause_requested") is True,
        "workers_running": int(status == "running"), "workers_idle": int(status == "idle"), "workers_paused": int(status == "paused"),
        "workers_stopped": int(status == "stopped"), "workers_failed": int(status == "failed"),
        "stale_workers": int(bool(value) and health.get("heartbeat_fresh") is not True)}

def project_runtime_mission(mission: Mapping[str, Any] | None) -> dict[str, Any]:
    """Read-only Mission projection. It never confirms, advances, enqueues, or writes."""
    value = _mapping(mission); goals = _mapping(value.get("goals")); status = value.get("mission_status")
    try:
        from core.runtime.runtime_mission_model import validate_mission
        valid = not validate_mission(value, check_expiry=False) if value else False
    except (TypeError, ValueError): valid = False
    count = lambda field: len(value.get(field) or [])
    total, completed = len(goals), count("completed_goal_ids")
    planner_ref=_mapping(value.get("planner_output_reference")); history=list(value.get("replanning_history") or [])
    planner_summary=_mapping(value.get("planner_output_summary"))
    return {"mission_present": bool(value), "mission_status": status, "mission_valid": valid,
        "mission_total_goals": total, "mission_ready_goals": count("ready_goal_ids"),
        "mission_running_goals": count("running_goal_ids"), "mission_waiting_goals": count("waiting_goal_ids"),
        "mission_completed_goals": completed, "mission_failed_goals": count("failed_goal_ids"),
        "mission_blocked_goals": count("blocked_goal_ids"), "mission_cancelled_goals": count("cancelled_goal_ids"),
        "mission_progress_percent": round(100 * completed / total, 2) if total else 0.0,
        "mission_waiting_for_plan_confirmation": status == "waiting_for_plan_confirmation",
        "mission_waiting_for_operator": status == "waiting_for_operator", "mission_partial_completion": status == "partially_completed",
        "mission_critical_failure": status == "failed" and any(_mapping(goal.get("failure")).get("critical") is True for goal in goals.values()),
        "mission_completed": status == "completed",
        "missions_created": int(bool(value)), "missions_waiting_plan": int(status == "waiting_for_plan_confirmation"),
        "missions_running": int(status in {"ready", "running"}), "missions_waiting_operator": int(status == "waiting_for_operator"),
        "missions_completed": int(status == "completed"), "missions_partial": int(status == "partially_completed"),
        "missions_blocked": int(status == "blocked"), "missions_failed": int(status == "failed"),
        "missions_cancelled": int(status == "cancelled"), "goals_total": total, "goals_ready": count("ready_goal_ids"),
        "goals_running": count("running_goal_ids"), "goals_completed": completed, "goals_failed": count("failed_goal_ids"),
        "goals_blocked": count("blocked_goal_ids"), "mission_planner_present":bool(planner_ref),
        "mission_planning_status":value.get("planning_status"),"mission_clarification_required":value.get("clarification_required") is True,
        "mission_plan_confirmation_required":status=="waiting_for_plan_confirmation","mission_replanning_required":value.get("replan_required") is True,
        "mission_replanning_status":value.get("replanning_status"),"mission_planning_revision":int(value.get("planning_revision")or 0),
        "mission_replanning_revision":int(value.get("replanning_revision")or 0),"planner_goal_count":int(planner_summary.get("goal_count")or len(goals)),
        "planner_risk_count":int(planner_summary.get("risk_count")or 0),"planner_unknown_scope_count":int(planner_summary.get("unknown_scope_count")or 0),
        "planner_operator_boundaries_count":int(planner_summary.get("operator_boundaries_count")or 0),"planner_memory_evidence_count":len(value.get("planner_evidence_references")or[]),
        "immutable_completed_goals_count":len(value.get("immutable_completed_goal_ids")or[]),"missions_planning":int(value.get("planning_status")=="planning"),
        "missions_waiting_clarification":int(value.get("clarification_required")is True),"missions_waiting_plan_confirmation":int(status=="waiting_for_plan_confirmation"),
        "missions_replanning":int(value.get("replanning_status")=="planning"),"missions_waiting_replan_confirmation":int(status=="waiting_for_replan_confirmation"),
        "planner_outputs_valid":int(bool(planner_ref) and valid),"planner_outputs_invalid":int(bool(planner_ref) and not valid),"planner_outputs_blocked":int(value.get("planning_status")=="blocked")}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _stable_reference(task: Any) -> str:
    if isinstance(task, Mapping) and _text(task.get("task_id")):
        return _text(task.get("task_id"))
    payload = json.dumps(task, ensure_ascii=False, sort_keys=True, default=str)
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"runtime-loop-task-{digest}"


def _normalize_task(task: Any) -> dict[str, Any]:
    if isinstance(task, str):
        return {"goal": _text(task), "task_id": "", "metadata": {}}
    payload = _mapping(task)
    return {
        "goal": _text(payload.get("goal")),
        "task_id": _text(payload.get("task_id")),
        "metadata": _mapping(payload.get("metadata")),
    }


def _task_snapshot(tasks: Any) -> list[Any]:
    if tasks is None:
        return []
    if isinstance(tasks, (str, Mapping)):
        return [deepcopy(tasks)]
    snapshot = getattr(tasks, "snapshot", None)
    if callable(snapshot):
        value = snapshot()
        return deepcopy(list(value)) if isinstance(value, (list, tuple)) else []
    if isinstance(tasks, (list, tuple)):
        return deepcopy(list(tasks))
    return []


def _changed_files(result: Mapping[str, Any]) -> list[str]:
    payload = _mapping(result)
    candidates = [
        payload.get("changed_files"),
        _mapping(payload.get("operator_result")).get("changed_files"),
        _mapping(
            _mapping(payload.get("operator_result")).get(
                "controlled_mutation_result"
            )
        ).get("changed_files"),
        _mapping(
            _mapping(payload.get("operator_result")).get(
                "governed_runtime_result"
            )
        ).get("applied_paths"),
    ]
    for candidate in candidates:
        if isinstance(candidate, (list, tuple)):
            return [_text(item) for item in candidate if _text(item)]
    return []


def _denial_reason(result: Mapping[str, Any]) -> str:
    payload = _mapping(result)
    operator = _mapping(payload.get("operator_result"))
    controlled = _mapping(operator.get("controlled_mutation_result"))
    for candidate in (
        payload.get("denial_reason"),
        operator.get("denial_reason"),
        controlled.get("denial_reason"),
    ):
        if _text(candidate):
            return _text(candidate)
    return ""


def _task_completed(result: Mapping[str, Any]) -> bool:
    payload = _mapping(result)
    if "task_completed" in payload:
        return payload.get("task_completed") is True
    if payload.get("ok") is not True:
        return False
    operator = _mapping(payload.get("operator_result"))
    controlled = _mapping(operator.get("controlled_mutation_result"))
    if controlled:
        return (
            controlled.get("ok") is True
            and controlled.get("mutation_completed") is True
            and controlled.get("validation_passed") is True
        )
    return True


def _advisory_metadata(
    task_metadata: Mapping[str, Any], result: Mapping[str, Any]
) -> dict[str, Any]:
    combined = _mapping(task_metadata)
    result_metadata = _mapping(result.get("metadata"))
    package_metadata = _mapping(_mapping(result.get("package")).get("metadata"))
    retained: dict[str, Any] = {}
    for key in ("memory_context", "decision_advice", "planner_advisor_bridge"):
        value = result_metadata.get(
            key, package_metadata.get(key, combined.get(key))
        )
        if isinstance(value, Mapping):
            retained[key] = _mapping(value)
    return {
        **retained,
        "read_only": True,
        "decision_authority": False,
        "requested_changes_modified": False,
    }


def _review_projection(metadata: Mapping[str, Any], execution_plan_required: bool) -> dict[str, Any]:
    plan = _mapping(metadata.get("execution_plan"))
    plan_built = (
        plan.get("schema") == "zero.runtime.apply_execution_plan.v1"
        and plan.get("plan_status") == "ready"
        and plan.get("plan_ready") is True
    )
    required = execution_plan_required or bool(plan)
    review = _mapping(
        metadata.get("execution_plan_review_result", metadata.get("execution_plan_review"))
    )
    review_status = "not_ready"
    admission_ready = False
    if plan_built:
        review_status = "pending"
        if review.get("contract") == "zero.runtime.execution_plan_review_gate.v1":
            projected = _text(review.get("review_status"))
            if projected in {"approved", "rejected", "invalid"}:
                review_status = projected
            admission_ready = (
                projected == "approved"
                and review.get("review_valid") is True
                and review.get("executor_admission_ready") is True
            )
    request = _mapping(metadata.get("operator_execution_request"))
    activation = _mapping(metadata.get("controlled_execution_result"))
    controlled_status = "not_ready"
    token_status = "not_issued"
    dry_run_status = "not_started"
    controlled_required = False
    if review_status == "approved" and admission_ready:
        controlled_required = True
        controlled_status = "operator_request_required" if not request else "ready_for_dry_run"
    if activation.get("contract") == "zero.runtime.controlled_execution_activation.v1":
        projected_activation = _text(activation.get("activation_status"))
        if projected_activation in {"completed", "blocked"}:
            controlled_required = True
            controlled_status = projected_activation
            token_status = _text(_mapping(activation.get("token")).get("token_status")) or "denied"
            dry_run_status = projected_activation
    active_request = _mapping(metadata.get("active_authorization"))
    active_result = _mapping(metadata.get("active_authorization_result"))
    active_required = controlled_status == "completed"
    active_status = "operator_authorization_required" if active_required else "not_ready"
    active_prepared = False
    if active_required and active_request:
        active_status = "pending"
    if active_result.get("contract") == "zero.runtime.active_execution_authorization.v1":
        projected_active = _text(active_result.get("authorization_status"))
        if projected_active in {"authorized", "rejected", "invalid"}:
            active_status = projected_active
            active_required = True
        active_prepared = (
            projected_active == "authorized"
            and active_result.get("authorization_valid") is True
            and active_result.get("active_execution_prepared") is True
        )
    invocation = _mapping(metadata.get("active_executor_invocation_request"))
    candidate = _mapping(metadata.get("candidate_mutation_bundle"))
    transaction = _mapping(metadata.get("transactional_execution_result"))
    transaction_required = active_prepared
    transaction_status = "not_ready"
    if active_prepared: transaction_status = "operator_invocation_required" if not invocation else "candidate_bundle_required" if not candidate else "ready"
    projected_tx = _text(transaction.get("transaction_status"))
    if projected_tx in {"committed", "rolled_back", "blocked", "rollback_failed"}:
        transaction_required = True
        transaction_status = "critical_failure" if projected_tx == "rollback_failed" else projected_tx
    return {
        "execution_plan_required": required,
        "execution_plan_status": "built" if plan_built else "not_built" if required else "not_required",
        "review_required": required,
        "review_status": review_status if required else "not_required",
        "executor_admission_ready": admission_ready,
        "execution_allowed": False,
        "execution_plan": plan if plan else None,
        "execution_plan_review": review if review else None,
        "controlled_execution_required": controlled_required,
        "controlled_execution_status": controlled_status,
        "executor_token_status": token_status,
        "dry_run_status": dry_run_status,
        "active_execution_ready": False,
        "operator_execution_request": request if request else None,
        "controlled_execution_result": activation if activation else None,
        "active_authorization_required": active_required,
        "active_authorization_status": active_status,
        "active_execution_prepared": active_prepared,
        "active_authorization": active_request if active_request else None,
        "active_authorization_result": active_result if active_result else None,
        "transactional_execution_required": transaction_required,
        "transactional_execution_status": transaction_status,
        "transaction_committed": transaction.get("transaction_committed") is True,
        "validation_executed": transaction.get("validation_executed") is True,
        "validation_passed": transaction.get("validation_passed"),
        "rollback_executed": transaction.get("rollback_executed") is True,
        "rollback_verified": transaction.get("rollback_verified"),
        "git_commit_performed": False,
        "active_executor_invocation_request": invocation if invocation else None,
        "candidate_mutation_bundle": candidate if candidate else None,
        "transactional_execution_result": transaction if transaction else None,
    }


@dataclass(frozen=True)
class RuntimeAutonomousLoop:
    task_runner: Any
    activity_memory: Any = None
    max_iterations: int = 10
    stop_on_error: bool = False
    observer: Any = None
    repair_advisor: Any = None
    bounded_repair_retry_loop: Any = None
    change_proposal_engine: Any = None
    approval_gate: Any = None

    def _run_task(self, goal: str) -> Mapping[str, Any]:
        if callable(self.task_runner):
            return self.task_runner(goal)
        runner = getattr(self.task_runner, "run", None)
        if callable(runner):
            return runner(goal)
        raise TypeError("task_runner_not_callable")

    def _run_bounded_retry(self, task: Mapping[str, Any]) -> Mapping[str, Any]:
        run = getattr(self.bounded_repair_retry_loop, "run", None)
        if not callable(run):
            raise TypeError("bounded_repair_retry_loop_not_callable")
        return run(deepcopy(task))

    def _record_activity(
        self,
        *,
        goal: str,
        task_reference: str,
        result: Mapping[str, Any],
    ) -> bool:
        append = getattr(self.activity_memory, "append", None)
        if not callable(append):
            return False
        try:
            recorded = append(
                goal=goal,
                task_id=task_reference,
                source="runtime_autonomous_loop",
                result=result,
                metadata={
                    "controlled": True,
                    "autonomous_task_creation": False,
                },
            )
        except Exception:
            return False
        return isinstance(recorded, Mapping) and (
            recorded.get("activity_status") == "recorded"
            or recorded.get("ok") is True
        )

    def _observe_workspace(
        self,
        *,
        goal: str,
        task_reference: str,
        changed_files: list[str],
        result: Mapping[str, Any],
    ) -> tuple[dict[str, Any], bool, str]:
        if self.observer is None:
            return {}, False, "disabled"
        try:
            observe = (
                self.observer
                if callable(self.observer)
                else getattr(self.observer, "observe", None)
            )
            if not callable(observe):
                raise TypeError("observer_not_callable")
            observation = _mapping(observe(
                goal=goal,
                task_id=task_reference,
                changed_files=deepcopy(changed_files),
                runner_result=_mapping(result),
            ))
            return (
                observation,
                observation.get("observation_complete") is True,
                _text(observation.get("observer_status")) or "observer_error",
            )
        except Exception as exc:
            return {
                "schema": "zero.runtime.workspace_observer.v1",
                "ok": False,
                "observer_status": "observer_error",
                "issues": [f"observer_error:{type(exc).__name__}"],
                "read_only": True,
                "mutation_allowed": False,
                "repair_allowed": False,
                "decision_authority": False,
                "requested_changes_modified": False,
                "observation_complete": False,
            }, False, "observer_error"

    def _advise_repair(
        self,
        *,
        goal: str,
        task_reference: str,
        result: Mapping[str, Any],
        observation: Mapping[str, Any],
        task_metadata: Mapping[str, Any],
    ) -> tuple[dict[str, Any], bool, str]:
        if self.repair_advisor is None:
            return {}, False, "disabled"
        try:
            advise = (
                self.repair_advisor
                if callable(self.repair_advisor)
                else getattr(self.repair_advisor, "advise", None)
            )
            if not callable(advise):
                raise TypeError("repair_advisor_not_callable")
            result_metadata = _mapping(result.get("metadata"))
            package_metadata = _mapping(
                _mapping(result.get("package")).get("metadata")
            )

            def advisory_value(key: str) -> dict[str, Any]:
                value = result_metadata.get(
                    key, package_metadata.get(key, task_metadata.get(key))
                )
                return _mapping(value)

            advice = _mapping(advise(
                goal=goal,
                task_id=task_reference,
                runner_result=_mapping(result),
                workspace_observation=_mapping(observation),
                memory_context=advisory_value("memory_context"),
                decision_advice=advisory_value("decision_advice"),
                planner_advisor_bridge=advisory_value(
                    "planner_advisor_bridge"
                ),
            ))
            status = _text(advice.get("advisor_status")) or "advisor_error"
            return advice, advice.get("repair_needed") is True, status
        except Exception as exc:
            return {
                "schema": "zero.runtime.repair_advisor.v1",
                "ok": False,
                "advisor_status": "advisor_error",
                "repair_needed": False,
                "repairability": "insufficient_evidence",
                "failure_category": "unknown_failure",
                "failure_reasons": [f"advisor_error:{type(exc).__name__}"],
                "repair_hints": ["request_operator_review"],
                "recommended_next_action": "request_operator_review",
                "confidence": 0.0,
                "source_summary": {},
                "risk_flags": [],
                "read_only": True,
                "repair_execution_allowed": False,
                "mutation_allowed": False,
                "decision_authority": False,
                "requested_changes_modified": False,
                "autonomous_retry_allowed": False,
                "patch_generation_allowed": False,
            }, False, "advisor_error"

    def _propose_change(
        self,
        *,
        goal: str,
        task_reference: str,
        result: Mapping[str, Any],
        observation: Mapping[str, Any],
        repair_advice: Mapping[str, Any],
        task_metadata: Mapping[str, Any],
    ) -> tuple[dict[str, Any], bool, str]:
        if self.change_proposal_engine is None:
            return {}, False, "disabled"
        try:
            propose = (
                self.change_proposal_engine
                if callable(self.change_proposal_engine)
                else getattr(self.change_proposal_engine, "propose", None)
            )
            if not callable(propose):
                raise TypeError("change_proposal_engine_not_callable")
            result_metadata = _mapping(result.get("metadata"))
            package_metadata = _mapping(
                _mapping(result.get("package")).get("metadata")
            )

            def advisory_value(key: str) -> dict[str, Any]:
                return _mapping(result_metadata.get(
                    key, package_metadata.get(key, task_metadata.get(key))
                ))

            proposal = _mapping(propose(
                goal=goal,
                task_id=task_reference,
                runner_result=_mapping(result),
                workspace_observation=_mapping(observation),
                repair_advice=_mapping(repair_advice),
                memory_context=advisory_value("memory_context"),
                decision_advice=advisory_value("decision_advice"),
                planner_advisor_bridge=advisory_value(
                    "planner_advisor_bridge"
                ),
            ))
            status = _text(proposal.get("proposal_status")) or "proposal_error"
            proposed = status in {
                "proposal_created", "manual_review_required",
                "proposal_blocked_by_safety",
            }
            return proposal, proposed, status
        except Exception as exc:
            return {
                "schema": "zero.runtime.change_proposal_engine.v1",
                "ok": False,
                "proposal_status": "proposal_error",
                "proposal_id": "",
                "proposal": {},
                "source_summary": {},
                "error_type": type(exc).__name__,
                "read_only": True,
                "mutation_allowed": False,
                "patch_generation_allowed": False,
                "repair_execution_allowed": False,
                "decision_authority": False,
                "requested_changes_modified": False,
                "autonomous_apply_allowed": False,
                "requires_operator_approval": True,
                "approval_status": "pending",
            }, False, "proposal_error"

    def _closed_result(
        self,
        *,
        loop_status: str,
        tasks_received: int,
        tasks_remaining: int,
        iteration_results: list[dict[str, Any]],
        stopped_reason: str,
    ) -> dict[str, Any]:
        completed = sum(
            item.get("task_completed") is True for item in iteration_results
        )
        failed = len(iteration_results) - completed
        return {
            "schema": RUNTIME_AUTONOMOUS_LOOP_SCHEMA,
            "ok": loop_status in {"completed", "empty_queue"},
            "loop_status": loop_status,
            "controlled": True,
            "autonomous_task_creation": False,
            "goal_mutation_allowed": False,
            "max_iterations": self.max_iterations,
            "iterations_completed": len(iteration_results),
            "tasks_received": tasks_received,
            "tasks_remaining": tasks_remaining,
            "completed_count": completed,
            "failed_count": failed,
            "stopped_reason": stopped_reason,
            "iteration_results": iteration_results,
            "runtime_loop_closed": True,
        }

    def run_mission(
        self,
        mission: Mapping[str, Any] | str | Path,
        *,
        scheduler_state_path: Any,
        worker_state_path: Any,
        worker_name: str,
        target_root: Any,
        workspace_root: Any,
        runtime_config: Mapping[str, Any] | None = None,
        max_iterations: int | None = None,
        lease_seconds: int | None = None,
        now_provider: Callable[[], Any] | None = None,
    ) -> dict[str, Any]:
        """
        Drive one persisted Mission through the existing Mission
        Orchestrator, Goal Execution Registry bridge, Worker Service, and
        Goal Executor.

        This method does not confirm plans, approve proposals, authorize
        active execution, create candidate bundles, or bypass transaction
        boundaries. A Mission that reaches an operator-controlled phase is
        returned as waiting rather than being advanced automatically.
        """
        from core.runtime.runtime_mission_execution_registry_bridge import (
            sync_mission_execution_registry,
        )
        from core.runtime.runtime_mission_model import load_mission
        from core.runtime.runtime_mission_orchestrator import (
            advance_mission,
        )
        from core.runtime.runtime_session_scheduler import LEASE_SECONDS
        from core.runtime.runtime_worker_service import (
            run_worker_iteration,
        )

        limit = self.max_iterations if max_iterations is None else max_iterations
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("invalid_mission_max_iterations")

        config = _mapping(runtime_config)
        config["target_root"] = target_root
        config["workspace_root"] = workspace_root
        clock = now_provider or (
            lambda: datetime.now(timezone.utc)
        )
        lifetime = LEASE_SECONDS if lease_seconds is None else lease_seconds

        if isinstance(mission, Mapping):
            current = _mapping(mission)
        else:
            current = load_mission(mission)

        mission_path = _text(current.get("mission_path"))
        if not mission_path:
            raise ValueError("mission_path_required")
        if not _text(current.get("scheduler_state_path")):
            current["scheduler_state_path"] = str(
                Path(scheduler_state_path).resolve(strict=False)
            )

        iterations: list[dict[str, Any]] = []
        stopped_reason = "iteration_limit_reached"

        terminal_statuses = {
            "completed",
            "partially_completed",
            "failed",
            "blocked",
            "cancelled",
            "expired",
        }
        operator_waiting_statuses = {
            "waiting_for_plan_confirmation",
            "waiting_for_replan_confirmation",
        }

        for index in range(1, limit + 1):
            now = clock()

            current = advance_mission(
                current,
                scheduler_state=scheduler_state_path,
                now=now,
                runtime_config=config,
            )

            status_before = _text(current.get("mission_status"))
            if status_before in terminal_statuses:
                stopped_reason = f"mission_{status_before}"
                iterations.append(
                    {
                        "iteration": index,
                        "mission_status_before": status_before,
                        "mission_status_after": status_before,
                        "registry_sync_performed": False,
                        "worker_iteration_performed": False,
                        "mission_projection": project_runtime_mission(
                            current
                        ),
                    }
                )
                break

            if status_before in operator_waiting_statuses:
                stopped_reason = status_before
                iterations.append(
                    {
                        "iteration": index,
                        "mission_status_before": status_before,
                        "mission_status_after": status_before,
                        "registry_sync_performed": False,
                        "worker_iteration_performed": False,
                        "mission_projection": project_runtime_mission(
                            current
                        ),
                    }
                )
                break

            bridge = sync_mission_execution_registry(
                current,
                target_root=target_root,
                workspace_root=workspace_root,
                runtime_config=config,
                now=now,
            )
            worker_config = _mapping(
                bridge.get("runtime_config_overlay")
            )

            worker = run_worker_iteration(
                scheduler_state_path=scheduler_state_path,
                worker_state_path=worker_state_path,
                worker_name=worker_name,
                target_root=target_root,
                workspace_root=workspace_root,
                now=now,
                lease_seconds=lifetime,
                runtime_config=worker_config,
            )

            current = advance_mission(
                current,
                scheduler_state=scheduler_state_path,
                now=now,
                runtime_config=config,
            )
            status_after = _text(current.get("mission_status"))

            iteration = {
                "iteration": index,
                "mission_status_before": status_before,
                "mission_status_after": status_after,
                "registry_sync_performed": True,
                "registered_session_ids": deepcopy(
                    bridge.get("registered_session_ids") or []
                ),
                "skipped_session_ids": deepcopy(
                    bridge.get("skipped_session_ids") or []
                ),
                "blocked_sessions": deepcopy(
                    bridge.get("blocked_sessions") or []
                ),
                "pending_request_count": int(
                    bridge.get("pending_request_count") or 0
                ),
                "registry_fingerprint": bridge.get(
                    "registry_fingerprint"
                ),
                "worker_iteration_performed": True,
                "worker_status": worker.get("worker_status"),
                "worker_last_result": deepcopy(
                    worker.get("last_result")
                ),
                "worker_projection": project_runtime_worker(
                    worker,
                    now=now,
                ),
                "mission_projection": project_runtime_mission(
                    current
                ),
            }
            iterations.append(iteration)

            if status_after in terminal_statuses:
                stopped_reason = f"mission_{status_after}"
                break
            if status_after in operator_waiting_statuses:
                stopped_reason = status_after
                break
            if worker.get("worker_status") == "failed":
                stopped_reason = "worker_failed"
                break

            last_result = _mapping(worker.get("last_result"))
            no_dispatch = (
                last_result.get("reason")
                == "no_dispatchable_session"
            )
            no_registry_work = (
                int(bridge.get("pending_request_count") or 0) == 0
                and not bridge.get("registered_session_ids")
            )
            if (
                no_dispatch
                and no_registry_work
                and status_after == status_before
            ):
                stopped_reason = "mission_waiting_for_external_input"
                break
        else:
            stopped_reason = "iteration_limit_reached"

        final_status = _text(current.get("mission_status"))
        completed = final_status == "completed"
        waiting = (
            final_status in operator_waiting_statuses
            or final_status == "waiting_for_operator"
            or stopped_reason == "mission_waiting_for_external_input"
        )
        return {
            "schema": RUNTIME_AUTONOMOUS_MISSION_DRIVER_SCHEMA,
            "ok": completed,
            "driver_status": (
                "completed"
                if completed
                else "waiting"
                if waiting
                else "stopped"
            ),
            "mission_id": current.get("mission_id"),
            "mission_path": mission_path,
            "mission_status": final_status,
            "iterations_completed": len(iterations),
            "max_iterations": limit,
            "stopped_reason": stopped_reason,
            "mission_completed": completed,
            "mission_waiting": waiting,
            "mission_terminal": final_status in terminal_statuses,
            "mission": deepcopy(current),
            "mission_projection": project_runtime_mission(current),
            "iteration_results": iterations,
            "runtime_loop_closed": True,
            "operator_boundaries_preserved": True,
            "autonomous_plan_confirmation": False,
            "autonomous_operator_approval": False,
            "autonomous_active_authorization": False,
            "autonomous_transaction_bypass": False,
        }

    def run_once(self, task: Any) -> dict[str, Any]:
        return self.run([task])

    def run(self, tasks: Sequence[Any] | Any | None) -> dict[str, Any]:
        queue = _task_snapshot(tasks)
        if not isinstance(self.max_iterations, int) or self.max_iterations <= 0:
            received = len(queue)
            return self._closed_result(
                loop_status="denied_invalid_configuration",
                tasks_received=received,
                tasks_remaining=received,
                iteration_results=[],
                stopped_reason="max_iterations_must_be_greater_than_zero",
            )

        tasks_received = len(queue)
        if not queue:
            return self._closed_result(
                loop_status="empty_queue",
                tasks_received=0,
                tasks_remaining=0,
                iteration_results=[],
                stopped_reason="queue_empty",
            )

        iterations: list[dict[str, Any]] = []
        runner_exception_seen = False
        stopped_on_error = False
        for index, raw_task in enumerate(queue[: self.max_iterations], start=1):
            task = _normalize_task(raw_task)
            goal = task["goal"]
            reference = task["task_id"] or _stable_reference(raw_task)
            started_at = _utc_now()
            error_type = ""
            if not goal:
                result: dict[str, Any] = {
                    "ok": False,
                    "denial_reason": "task_goal_required",
                }
            else:
                try:
                    if self.bounded_repair_retry_loop is not None:
                        bounded_task = deepcopy(task)
                        bounded_task["task_id"] = reference
                        result = _mapping(self._run_bounded_retry(bounded_task))
                    else:
                        result = _mapping(self._run_task(goal))
                except Exception as exc:
                    runner_exception_seen = True
                    error_type = type(exc).__name__
                    result = {
                        "ok": False,
                        "denial_reason": f"runner_error:{error_type}",
                        "error_type": error_type,
                    }

            completed = _task_completed(result)
            changed_files = _changed_files(result)
            bounded_result = (
                _mapping(result)
                if result.get("schema")
                == "zero.runtime.bounded_repair_retry_loop.v1"
                else {}
            )
            if bounded_result:
                attempt_results = bounded_result.get("attempt_results")
                attempt_results = (
                    attempt_results if isinstance(attempt_results, list) else []
                )
                final_attempt = _mapping(
                    attempt_results[-1] if attempt_results else {}
                )
                observation = _mapping(
                    final_attempt.get("workspace_observation")
                )
                observed = observation.get("observation_complete") is True
                observation_status = (
                    _text(observation.get("observer_status")) or "disabled"
                )
                repair_advice = _mapping(final_attempt.get("repair_advice"))
                repair_advised = repair_advice.get("repair_needed") is True
                repair_status = (
                    _text(repair_advice.get("advisor_status")) or "disabled"
                )
            else:
                observation, observed, observation_status = self._observe_workspace(
                    goal=goal,
                    task_reference=reference,
                    changed_files=changed_files,
                    result=result,
                )
                repair_advice, repair_advised, repair_status = self._advise_repair(
                    goal=goal,
                    task_reference=reference,
                    result=result,
                    observation=observation,
                    task_metadata=task["metadata"],
                )
            change_proposal, change_proposed, proposal_status = self._propose_change(
                goal=goal,
                task_reference=reference,
                result=result,
                observation=observation,
                repair_advice=repair_advice,
                task_metadata=task["metadata"],
            )
            approval_required = change_proposed
            approval_status = "pending" if approval_required else "not_required"
            review_projection = _review_projection(task["metadata"], approval_required)
            iteration = {
                "iteration": index,
                "task_id": reference,
                "task_reference": reference,
                "goal": goal,
                "metadata": deepcopy(task["metadata"]),
                "runner_ok": result.get("ok") is True,
                "task_completed": completed,
                "changed_files": changed_files,
                "denial_reason": _denial_reason(result),
                "error_type": error_type,
                "activity_recorded": self._record_activity(
                    goal=goal,
                    task_reference=reference,
                    result=result,
                ) if goal else False,
                "started_at": started_at,
                "completed_at": _utc_now(),
                "loop_continues": True,
                "advisory_metadata": _advisory_metadata(
                    task["metadata"], result
                ),
                "workspace_observation": observation,
                "workspace_observed": observed,
                "observation_status": observation_status,
                "repair_advice": repair_advice,
                "repair_advised": repair_advised,
                "repair_advisor_status": repair_status,
                "bounded_retry_result": bounded_result,
                "change_proposal": change_proposal,
                "change_proposed": change_proposed,
                "change_proposal_status": proposal_status,
                "approval_required": approval_required,
                "approval_status": approval_status,
                "operator_approval": None,
                "apply_admission_required": approval_required,
                "apply_admission_status": "not_evaluated" if approval_required else "not_required",
                **review_projection,
            }
            iterations.append(iteration)

            if error_type and self.stop_on_error:
                iteration["loop_continues"] = False
                stopped_on_error = True
                break

        tasks_remaining = tasks_received - len(iterations)
        if stopped_on_error:
            loop_status = "runner_error"
            stopped_reason = "runner_error_stop_on_error"
        elif tasks_remaining > 0:
            loop_status = "iteration_limit_reached"
            stopped_reason = "iteration_limit_reached"
        elif any(not item["task_completed"] for item in iterations):
            loop_status = "completed_with_failures"
            stopped_reason = (
                "runner_errors_continued"
                if runner_exception_seen
                else "tasks_completed_with_failures"
            )
        else:
            loop_status = "completed"
            stopped_reason = "queue_exhausted"

        if iterations:
            iterations[-1]["loop_continues"] = False
        return self._closed_result(
            loop_status=loop_status,
            tasks_received=tasks_received,
            tasks_remaining=tasks_remaining,
            iteration_results=iterations,
            stopped_reason=stopped_reason,
        )


__all__ = [
    "RUNTIME_AUTONOMOUS_LOOP_SCHEMA",
    "RUNTIME_AUTONOMOUS_MISSION_DRIVER_SCHEMA",
    "RuntimeAutonomousLoop",
    "project_runtime_session",
    "project_runtime_mission",
    "project_runtime_scheduler",
    "project_runtime_worker",
]
