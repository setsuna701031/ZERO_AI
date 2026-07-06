from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_WORK_CYCLE_COORDINATOR_SCHEMA = "zero.runtime.work_cycle_coordinator.v1"

WORK_CYCLE_STATUSES = (
    "coordinated",
    "blocked",
    "stopped",
    "recovery_required",
    "denied",
)

WORK_CYCLE_DECISIONS = ("continue", "stop", "wait", "recover", "deny")

REQUIRED_WORK_CYCLE_FIELDS = (
    "work_cycle_request_id",
    "runtime_session_id",
    "execution_lease_id",
    "capability_grant_id",
    "executor_binding_id",
    "loop_controller",
    "execution_tick",
    "task_admission_id",
    "dispatch_commit",
    "executor_invocation_boundary",
    "audit_required",
)

WORK_CYCLE_LOCKS = {
    "record_only": True,
    "decision_only": True,
    "executor_run_allowed": False,
    "task_execution_allowed": False,
    "tool_invocation_allowed": False,
    "subprocess_allowed": False,
    "shell_allowed": False,
    "network_allowed": False,
    "filesystem_mutation_allowed": False,
    "state_mutation_allowed": False,
    "task_completion_allowed": False,
    "autonomy_loop_allowed": False,
    "self_start_allowed": False,
    "background_worker_allowed": False,
}


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _missing_required_fields(record: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_WORK_CYCLE_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in WORK_CYCLE_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _work_cycle_id(
    *,
    request_id: str,
    runtime_session_id: str,
    loop_controller_id: str,
    execution_tick_id: str,
    dispatch_commit_id: str,
    executor_invocation_id: str,
) -> str:
    fragment = _stable_fragment(
        {
            "request_id": request_id,
            "runtime_session_id": runtime_session_id,
            "loop_controller_id": loop_controller_id,
            "execution_tick_id": execution_tick_id,
            "dispatch_commit_id": dispatch_commit_id,
            "executor_invocation_id": executor_invocation_id,
        }
    )
    return (
        f"runtime-work-cycle::{runtime_session_id}::"
        f"{loop_controller_id}::{fragment}"
    )


def build_runtime_work_cycle_request(
    *,
    work_cycle_request_id: str,
    runtime_session_id: str | None = None,
    execution_lease_id: str | None = None,
    capability_grant_id: str | None = None,
    executor_binding_id: str | None = None,
    loop_controller: dict[str, Any] | None = None,
    execution_tick: dict[str, Any] | None = None,
    task_admission_id: str | None = None,
    dispatch_commit: dict[str, Any] | None = None,
    executor_invocation_boundary: dict[str, Any] | None = None,
    cycle_reason: str = "explicit_runtime_work_cycle_coordination",
    cycle_time: str = "deterministic-time::1361",
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_WORK_CYCLE_COORDINATOR_SCHEMA,
        "work_cycle_request_id": work_cycle_request_id,
        "runtime_session_id": runtime_session_id,
        "execution_lease_id": execution_lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_binding_id": executor_binding_id,
        "loop_controller": _as_mapping(loop_controller),
        "execution_tick": _as_mapping(execution_tick),
        "task_admission_id": task_admission_id,
        "dispatch_commit": _as_mapping(dispatch_commit),
        "executor_invocation_boundary": _as_mapping(executor_invocation_boundary),
        "cycle_reason": cycle_reason,
        "cycle_time": cycle_time,
        "boundary_locks": deepcopy(WORK_CYCLE_LOCKS),
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


def _status_is(record: dict[str, Any], *fields: str, statuses: set[str]) -> bool:
    return any(record.get(field) in statuses for field in fields)


def _upstream_recovery_required(*records: dict[str, Any]) -> bool:
    return any(
        record.get("recovery_required") is True
        or _status_is(
            record,
            *(
                "loop_status",
                "tick_status",
                "commit_status",
                "invocation_status",
                "task_admission_status",
            ),
            statuses={"recovery_required"},
        )
        for record in records
    )


def _upstream_stop_requested(loop: dict[str, Any], tick: dict[str, Any]) -> bool:
    loop_decision = _as_mapping(loop.get("loop_decision"))
    tick_decision = _as_mapping(tick.get("tick_decision"))
    return (
        loop.get("loop_status") == "stopped"
        or loop.get("stop_requested") is True
        or loop_decision.get("cycle_decision") == "stop"
        or loop_decision.get("decision") == "stop"
        or tick_decision.get("cycle_decision") == "stop"
        or tick_decision.get("decision") == "stop"
    )


def _evaluate_runtime_work_cycle_request(record: dict[str, Any]) -> dict[str, Any]:
    loop = _as_mapping(record.get("loop_controller"))
    tick = _as_mapping(record.get("execution_tick"))
    commit = _as_mapping(record.get("dispatch_commit"))
    boundary = _as_mapping(record.get("executor_invocation_boundary"))

    runtime_session_id = record.get("runtime_session_id")
    execution_lease_id = record.get("execution_lease_id")
    capability_grant_id = record.get("capability_grant_id")
    executor_binding_id = record.get("executor_binding_id")
    task_admission_id = record.get("task_admission_id")
    loop_controller_id = loop.get("loop_controller_id")
    execution_tick_id = tick.get("execution_tick_id")
    dispatch_commit_id = commit.get("dispatch_commit_id")
    executor_invocation_id = boundary.get("executor_invocation_id")

    loop_controlled = (
        bool(loop_controller_id)
        and loop.get("loop_status") == "controlled"
        and loop.get("loop_ready") is True
        and loop.get("record_only") is True
        and loop.get("executor_run_performed") is False
        and loop.get("task_execution_performed") is False
        and loop.get("tool_invoked") is False
        and loop.get("filesystem_mutation_performed") is False
        and loop.get("state_mutation_performed") is False
    )
    tick_valid = (
        bool(execution_tick_id)
        and tick.get("tick_status") == "ticked"
        and tick.get("tick_ready") is True
        and tick.get("record_only") is True
        and tick.get("single_cycle_only") is True
        and tick.get("continuation_allowed") is False
    )
    commit_valid = (
        bool(dispatch_commit_id)
        and commit.get("commit_status") == "committed"
        and commit.get("dispatch_ready") is True
        and commit.get("record_only") is True
    )
    boundary_valid = (
        bool(executor_invocation_id)
        and boundary.get("invocation_status") == "bounded"
        and boundary.get("boundary_ready") is True
        and boundary.get("record_only") is True
    )

    problems: list[str] = []
    denied_upstream = False
    expired_or_revoked_upstream = False
    stale_tick = False

    if not loop_controller_id:
        problems.append("missing_loop_controller")
    elif loop.get("loop_status") == "denied":
        problems.append("denied_loop_controller")
        denied_upstream = True
    elif loop.get("loop_status") in {"expired", "revoked"}:
        problems.append(f"{loop.get('loop_status')}_loop_controller")
        expired_or_revoked_upstream = True
    elif loop.get("loop_status") not in {"controlled", "stopped"}:
        problems.append("loop_controller_not_controlled")
    elif not loop_controlled and loop.get("loop_status") != "stopped":
        problems.append("loop_controller_not_ready")

    if not execution_tick_id:
        problems.append("missing_execution_tick")
    elif tick.get("tick_status") == "denied":
        problems.append("denied_execution_tick")
        denied_upstream = True
    elif tick.get("tick_status") in {"expired", "revoked"}:
        problems.append(f"{tick.get('tick_status')}_execution_tick")
        expired_or_revoked_upstream = True
    elif tick.get("tick_stale") is True or tick.get("stale") is True:
        problems.append("stale_execution_tick")
        stale_tick = True
    elif not tick_valid:
        problems.append("execution_tick_not_ticked")

    if not dispatch_commit_id:
        problems.append("missing_dispatch_commit")
    elif commit.get("commit_status") == "denied":
        problems.append("denied_dispatch_commit")
        denied_upstream = True
    elif commit.get("commit_status") in {"expired", "revoked"}:
        problems.append(f"{commit.get('commit_status')}_dispatch_commit")
        expired_or_revoked_upstream = True
    elif not commit_valid:
        problems.append("dispatch_commit_not_committed")

    if not executor_invocation_id:
        problems.append("missing_executor_invocation_boundary")
    elif boundary.get("invocation_status") == "denied":
        problems.append("denied_executor_invocation_boundary")
        denied_upstream = True
    elif boundary.get("invocation_status") in {"expired", "revoked"}:
        problems.append(f"{boundary.get('invocation_status')}_executor_invocation_boundary")
        expired_or_revoked_upstream = True
    elif not boundary_valid:
        problems.append("executor_invocation_boundary_not_bounded")

    expected_matches = (
        ("runtime_session_id", runtime_session_id),
        ("execution_lease_id", execution_lease_id),
        ("capability_grant_id", capability_grant_id),
        ("executor_binding_id", executor_binding_id),
        ("task_admission_id", task_admission_id),
        ("dispatch_commit_id", dispatch_commit_id),
    )
    for field, expected in expected_matches:
        if not expected:
            problems.append(f"missing_{field}")
            continue
        for name, upstream in (
            ("loop_controller", loop),
            ("execution_tick", tick),
            ("dispatch_commit", commit),
            ("executor_invocation_boundary", boundary),
        ):
            if field in upstream and upstream.get(field) != expected:
                problems.append(f"{name}_{field}_mismatch")

    if loop.get("execution_tick_id") and loop.get("execution_tick_id") != execution_tick_id:
        problems.append("loop_controller_execution_tick_mismatch")
    if tick.get("executor_invocation_id") and tick.get("executor_invocation_id") != executor_invocation_id:
        problems.append("execution_tick_invocation_boundary_mismatch")
    if boundary.get("dispatch_commit_id") and boundary.get("dispatch_commit_id") != dispatch_commit_id:
        problems.append("executor_invocation_dispatch_commit_mismatch")

    recovery_required = _upstream_recovery_required(loop, tick, commit, boundary)
    stopped = _upstream_stop_requested(loop, tick)

    return {
        "loop_controller_id": loop_controller_id,
        "execution_tick_id": execution_tick_id,
        "task_admission_id": task_admission_id,
        "dispatch_commit_id": dispatch_commit_id,
        "executor_invocation_id": executor_invocation_id,
        "runtime_session_id": runtime_session_id,
        "execution_lease_id": execution_lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_binding_id": executor_binding_id,
        "problems": list(dict.fromkeys(problems)),
        "denied_upstream": denied_upstream,
        "expired_or_revoked_upstream": expired_or_revoked_upstream,
        "stale_tick": stale_tick,
        "recovery_required": recovery_required,
        "stopped": stopped,
    }


def validate_runtime_work_cycle_request(request: dict[str, Any]) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    evaluation = _evaluate_runtime_work_cycle_request(record)
    problems = list(evaluation["problems"])
    if missing:
        problems.append("missing_required_fields")
    if unlocks:
        problems.append("boundary_unlock_attempt")
    if record.get("audit_required") is not True:
        problems.append("audit_not_required")
    if record.get("non_mainline_issue_reporting_required") is not True:
        problems.append("non_mainline_issue_reporting_not_required")
    problems = list(dict.fromkeys(problems))

    if evaluation["recovery_required"]:
        status = "recovery_required"
        decision = "recover"
        next_action = "enter_recovery_coordination"
        stop_reason = "upstream_recovery_required"
    elif evaluation["stopped"]:
        status = "stopped"
        decision = "stop"
        next_action = "stop_work_cycle"
        stop_reason = "upstream_stop"
    elif evaluation["denied_upstream"] or "boundary_unlock_attempt" in problems:
        status = "denied"
        decision = "deny"
        next_action = "deny_work_cycle"
        stop_reason = "upstream_denied"
    elif problems or evaluation["expired_or_revoked_upstream"] or evaluation["stale_tick"]:
        status = "blocked"
        decision = "wait"
        next_action = "wait_for_valid_runtime_authority_chain"
        stop_reason = "blocked_runtime_authority_chain"
    else:
        status = "coordinated"
        decision = "continue"
        next_action = "return_controlled_cycle_decision"
        stop_reason = "none"

    return {
        "schema": RUNTIME_WORK_CYCLE_COORDINATOR_SCHEMA,
        "valid": not problems and status == "coordinated",
        "work_cycle_request_id": record.get("work_cycle_request_id"),
        "cycle_status": status,
        "cycle_decision": decision,
        "next_action": next_action,
        "stop_reason": stop_reason,
        "recovery_required": status == "recovery_required",
        "denial_reason": "none" if not problems else ";".join(problems),
        "problems": problems,
        "missing_required_fields": missing,
        "unlock_attempts": unlocks,
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "filesystem_mutation_performed": False,
        "state_mutation_performed": False,
        "task_completed": False,
        "autonomy_loop_started": False,
        "self_start_performed": False,
        "background_worker_started": False,
        **evaluation,
    }


def _cycle_decision_record(validation: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision_type": "runtime_work_cycle_record_only",
        "cycle_decision": validation["cycle_decision"],
        "next_action": validation["next_action"],
        "stop_reason": validation["stop_reason"],
        "recovery_required": validation["recovery_required"],
        "executor_run_allowed": False,
        "task_execution_allowed": False,
        "tool_invocation_allowed": False,
        "subprocess_allowed": False,
        "shell_allowed": False,
        "network_allowed": False,
        "filesystem_mutation_allowed": False,
        "state_mutation_allowed": False,
        "task_completion_allowed": False,
        "autonomy_loop_allowed": False,
        "self_start_allowed": False,
        "background_worker_allowed": False,
    }


def build_runtime_work_cycle_record(request: dict[str, Any]) -> dict[str, Any]:
    validation = validate_runtime_work_cycle_request(request)
    record = _as_mapping(request)
    work_cycle_id = _work_cycle_id(
        request_id=str(validation.get("work_cycle_request_id") or "missing-request"),
        runtime_session_id=str(validation.get("runtime_session_id") or "missing-session"),
        loop_controller_id=str(validation.get("loop_controller_id") or "missing-loop"),
        execution_tick_id=str(validation.get("execution_tick_id") or "missing-tick"),
        dispatch_commit_id=str(validation.get("dispatch_commit_id") or "missing-commit"),
        executor_invocation_id=str(
            validation.get("executor_invocation_id") or "missing-invocation"
        ),
    )
    cycle = {
        "schema": RUNTIME_WORK_CYCLE_COORDINATOR_SCHEMA,
        "work_cycle_id": work_cycle_id,
        "work_cycle_request_id": validation.get("work_cycle_request_id"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "loop_controller_id": validation.get("loop_controller_id"),
        "execution_tick_id": validation.get("execution_tick_id"),
        "task_admission_id": validation.get("task_admission_id"),
        "dispatch_commit_id": validation.get("dispatch_commit_id"),
        "executor_invocation_boundary_id": validation.get("executor_invocation_id"),
        "cycle_status": validation["cycle_status"],
        "cycle_decision": validation["cycle_decision"],
        "next_action": validation["next_action"],
        "stop_reason": validation["stop_reason"],
        "recovery_required": validation["recovery_required"],
        "cycle_reason": record.get("cycle_reason"),
        "cycle_time": record.get("cycle_time"),
        "decision_record": _cycle_decision_record(validation),
        "denial_reason": validation["denial_reason"],
        "supported_statuses": list(WORK_CYCLE_STATUSES),
        "supported_decisions": list(WORK_CYCLE_DECISIONS),
        "record_only": True,
        "coordination_only": True,
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "filesystem_mutation_performed": False,
        "state_mutation_performed": False,
        "task_completed": False,
        "autonomy_loop_started": False,
        "self_start_performed": False,
        "background_worker_started": False,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }
    cycle["audit_projection"] = build_runtime_work_cycle_audit_projection(cycle)
    return cycle


def build_runtime_work_cycle_audit_projection(
    work_cycle_record: dict[str, Any] | None,
) -> dict[str, Any]:
    cycle = _as_mapping(work_cycle_record)
    return {
        "projection": "runtime_work_cycle_coordinator_audit",
        "projection_only": True,
        "work_cycle_id": cycle.get("work_cycle_id"),
        "runtime_session_id": cycle.get("runtime_session_id"),
        "loop_controller_id": cycle.get("loop_controller_id"),
        "execution_tick_id": cycle.get("execution_tick_id"),
        "task_admission_id": cycle.get("task_admission_id"),
        "dispatch_commit_id": cycle.get("dispatch_commit_id"),
        "executor_invocation_boundary_id": cycle.get(
            "executor_invocation_boundary_id"
        ),
        "cycle_status": cycle.get("cycle_status", "denied"),
        "cycle_decision": cycle.get("cycle_decision", "deny"),
        "next_action": cycle.get("next_action", "deny_work_cycle"),
        "stop_reason": cycle.get("stop_reason", "not_evaluated"),
        "recovery_required": cycle.get("recovery_required") is True,
        "decision_record": _as_mapping(cycle.get("decision_record")),
        "coordinated_record_only": cycle.get("cycle_status") == "coordinated",
        "coordination_only": True,
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "filesystem_mutation_performed": False,
        "state_mutation_performed": False,
        "task_completed": False,
        "autonomy_loop_started": False,
        "self_start_performed": False,
        "background_worker_started": False,
    }


def can_runtime_work_cycle_act(work_cycle_record: dict[str, Any]) -> dict[str, Any]:
    cycle = _as_mapping(work_cycle_record)
    return {
        "work_cycle_id": cycle.get("work_cycle_id"),
        "cycle_status": cycle.get("cycle_status", "denied"),
        "cycle_decision": cycle.get("cycle_decision", "deny"),
        "can_return_decision": cycle.get("cycle_status") == "coordinated",
        "can_run_executor": False,
        "can_execute_task": False,
        "can_invoke_tools": False,
        "can_mutate_filesystem": False,
        "can_start_background_loop": False,
        "blocked_reason": "runtime_work_cycle_execution_disabled",
    }


def build_runtime_work_cycle_audit_record(request: dict[str, Any]) -> dict[str, Any]:
    validation = validate_runtime_work_cycle_request(request)
    cycle = build_runtime_work_cycle_record(request)
    return {
        "audit_schema": RUNTIME_WORK_CYCLE_COORDINATOR_SCHEMA + ".audit",
        "decision": "reserved_runtime_work_cycle_coordination_record_only",
        "work_cycle_request_id": validation.get("work_cycle_request_id"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "loop_controller_id": validation.get("loop_controller_id"),
        "execution_tick_id": validation.get("execution_tick_id"),
        "task_admission_id": validation.get("task_admission_id"),
        "dispatch_commit_id": validation.get("dispatch_commit_id"),
        "executor_invocation_boundary_id": validation.get("executor_invocation_id"),
        "request_valid": validation["valid"],
        "runtime_work_cycle_record": cycle,
        "audit_projection": cycle["audit_projection"],
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "filesystem_mutation_performed": False,
        "state_mutation_performed": False,
        "task_completed": False,
        "autonomy_loop_started": False,
        "self_start_performed": False,
        "background_worker_started": False,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
        "non_mainline_issues": validation["problems"],
    }


def build_runtime_work_cycle_milestone_seal(request: dict[str, Any]) -> dict[str, Any]:
    audit = build_runtime_work_cycle_audit_record(request)
    cycle = _as_mapping(audit.get("runtime_work_cycle_record"))
    return {
        "seal": "runtime_work_cycle_coordinator_bundle",
        "schema": RUNTIME_WORK_CYCLE_COORDINATOR_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_RUNTIME_WORK_CYCLE_COORDINATION_RECORDS_ONLY",
        "work_cycle_id": cycle.get("work_cycle_id"),
        "loop_controller_id": cycle.get("loop_controller_id"),
        "execution_tick_id": cycle.get("execution_tick_id"),
        "dispatch_commit_id": cycle.get("dispatch_commit_id"),
        "executor_invocation_boundary_id": cycle.get(
            "executor_invocation_boundary_id"
        ),
        "cycle_status": cycle.get("cycle_status"),
        "cycle_decision": cycle.get("cycle_decision"),
        "audit_decision": audit["decision"],
        "coordination_only": True,
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "filesystem_mutation_performed": False,
        "state_mutation_performed": False,
        "task_completed": False,
        "autonomy_loop_started": False,
        "self_start_performed": False,
        "background_worker_started": False,
        "forbidden_surfaces_locked": True,
        "audit_required": True,
    }


__all__ = [
    "RUNTIME_WORK_CYCLE_COORDINATOR_SCHEMA",
    "WORK_CYCLE_STATUSES",
    "WORK_CYCLE_DECISIONS",
    "REQUIRED_WORK_CYCLE_FIELDS",
    "WORK_CYCLE_LOCKS",
    "build_runtime_work_cycle_request",
    "validate_runtime_work_cycle_request",
    "build_runtime_work_cycle_record",
    "build_runtime_work_cycle_audit_projection",
    "can_runtime_work_cycle_act",
    "build_runtime_work_cycle_audit_record",
    "build_runtime_work_cycle_milestone_seal",
]
