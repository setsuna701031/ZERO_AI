from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_STEP_EXECUTOR_BRIDGE_SCHEMA = "zero.runtime.step_executor_bridge.v1"

STEP_BRIDGE_STATUSES = ("bridged", "denied", "blocked", "expired", "revoked")

STEP_REQUEST_TYPES = (
    "read_step",
    "write_step",
    "mutation_step",
    "recovery_step",
    "noop_step",
)

REQUIRED_STEP_BRIDGE_FIELDS = (
    "step_bridge_request_id",
    "runtime_session_id",
    "execution_lease_id",
    "capability_grant_id",
    "executor_binding_id",
    "loop_controller_id",
    "execution_tick_id",
    "work_cycle",
    "step_request_type",
    "audit_required",
)

STEP_BRIDGE_LOCKS = {
    "record_only": True,
    "bridge_only": True,
    "executor_run_allowed": False,
    "step_execution_allowed": False,
    "task_execution_allowed": False,
    "tool_invocation_allowed": False,
    "subprocess_allowed": False,
    "shell_allowed": False,
    "network_allowed": False,
    "filesystem_read_allowed": False,
    "filesystem_write_allowed": False,
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
    return [field for field in REQUIRED_STEP_BRIDGE_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in STEP_BRIDGE_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _step_bridge_id(
    *,
    request_id: str,
    runtime_session_id: str,
    work_cycle_id: str,
    execution_tick_id: str,
    executor_binding_id: str,
    step_request_type: str,
) -> str:
    fragment = _stable_fragment(
        {
            "request_id": request_id,
            "runtime_session_id": runtime_session_id,
            "work_cycle_id": work_cycle_id,
            "execution_tick_id": execution_tick_id,
            "executor_binding_id": executor_binding_id,
            "step_request_type": step_request_type,
        }
    )
    return (
        f"runtime-step-bridge::{runtime_session_id}::"
        f"{work_cycle_id}::{fragment}"
    )


def _step_request_id(
    *,
    runtime_session_id: str,
    work_cycle_id: str,
    execution_tick_id: str,
    executor_binding_id: str,
    step_request_type: str,
) -> str:
    fragment = _stable_fragment(
        {
            "runtime_session_id": runtime_session_id,
            "work_cycle_id": work_cycle_id,
            "execution_tick_id": execution_tick_id,
            "executor_binding_id": executor_binding_id,
            "step_request_type": step_request_type,
        }
    )
    return (
        f"runtime-step-request::{runtime_session_id}::"
        f"{execution_tick_id}::{step_request_type}::{fragment}"
    )


def build_runtime_step_executor_bridge_request(
    *,
    step_bridge_request_id: str,
    runtime_session_id: str | None = None,
    execution_lease_id: str | None = None,
    capability_grant_id: str | None = None,
    executor_binding_id: str | None = None,
    loop_controller_id: str | None = None,
    execution_tick_id: str | None = None,
    work_cycle: dict[str, Any] | None = None,
    step_request_type: str = "noop_step",
    next_step_intent: str = "prepare_step_executor_request_record",
    bridge_reason: str = "explicit_runtime_step_executor_bridge",
    bridge_time: str = "deterministic-time::1369",
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_STEP_EXECUTOR_BRIDGE_SCHEMA,
        "step_bridge_request_id": step_bridge_request_id,
        "runtime_session_id": runtime_session_id,
        "execution_lease_id": execution_lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_binding_id": executor_binding_id,
        "loop_controller_id": loop_controller_id,
        "execution_tick_id": execution_tick_id,
        "work_cycle": _as_mapping(work_cycle),
        "step_request_type": step_request_type,
        "next_step_intent": next_step_intent,
        "bridge_reason": bridge_reason,
        "bridge_time": bridge_time,
        "boundary_locks": deepcopy(STEP_BRIDGE_LOCKS),
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


def _has_expired_or_revoked_upstream(cycle: dict[str, Any]) -> tuple[bool, str | None]:
    if cycle.get("cycle_status") in {"expired", "revoked"}:
        return True, f"{cycle.get('cycle_status')}_work_cycle"
    for key, value in _as_mapping(cycle.get("upstream_statuses")).items():
        if value in {"expired", "revoked"}:
            return True, f"{value}_{key}"
    for field in (
        "loop_status",
        "tick_status",
        "commit_status",
        "invocation_status",
        "lease_status",
        "grant_status",
        "binding_status",
    ):
        if cycle.get(field) in {"expired", "revoked"}:
            return True, f"{cycle.get(field)}_{field}"
    return False, None


def _evaluate_runtime_step_executor_bridge_request(
    record: dict[str, Any],
) -> dict[str, Any]:
    cycle = _as_mapping(record.get("work_cycle"))

    runtime_session_id = record.get("runtime_session_id")
    execution_lease_id = record.get("execution_lease_id")
    capability_grant_id = record.get("capability_grant_id")
    executor_binding_id = record.get("executor_binding_id")
    loop_controller_id = record.get("loop_controller_id")
    execution_tick_id = record.get("execution_tick_id")
    work_cycle_id = cycle.get("work_cycle_id")
    step_request_type = record.get("step_request_type")

    problems: list[str] = []
    if not work_cycle_id:
        problems.append("missing_work_cycle")
    if not runtime_session_id:
        problems.append("missing_runtime_session_id")
    if not execution_lease_id:
        problems.append("missing_execution_lease_id")
    if not capability_grant_id:
        problems.append("missing_capability_grant_id")
    if not executor_binding_id:
        problems.append("missing_executor_binding_id")
    if not loop_controller_id:
        problems.append("missing_loop_controller_id")
    if not execution_tick_id:
        problems.append("missing_execution_tick_id")
    if step_request_type not in STEP_REQUEST_TYPES:
        problems.append("unsupported_step_request_type")

    for field, expected in (
        ("runtime_session_id", runtime_session_id),
        ("execution_lease_id", execution_lease_id),
        ("capability_grant_id", capability_grant_id),
        ("executor_binding_id", executor_binding_id),
        ("loop_controller_id", loop_controller_id),
        ("execution_tick_id", execution_tick_id),
    ):
        if field in cycle and cycle.get(field) != expected:
            problems.append(f"work_cycle_{field}_mismatch")

    cycle_status = cycle.get("cycle_status")
    cycle_decision = cycle.get("cycle_decision")
    recovery_required = cycle.get("recovery_required") is True
    expired_or_revoked, expired_or_revoked_reason = _has_expired_or_revoked_upstream(
        cycle
    )

    if cycle_status == "stopped":
        problems.append("stopped_work_cycle")
    elif cycle_status == "denied":
        problems.append("denied_work_cycle")
    elif cycle_status == "recovery_required" or recovery_required:
        problems.append("recovery_required_work_cycle")
    elif expired_or_revoked and expired_or_revoked_reason:
        problems.append(expired_or_revoked_reason)
    elif work_cycle_id and (
        cycle_status != "coordinated" or cycle_decision != "continue"
    ):
        problems.append("work_cycle_not_coordinated_continue")

    if cycle.get("record_only") is not True and work_cycle_id:
        problems.append("work_cycle_not_record_only")
    if cycle.get("task_execution_performed") is not False and work_cycle_id:
        problems.append("work_cycle_task_execution_detected")
    if cycle.get("tool_invoked") is not False and work_cycle_id:
        problems.append("work_cycle_tool_invocation_detected")
    if cycle.get("filesystem_mutation_performed") is not False and work_cycle_id:
        problems.append("work_cycle_filesystem_mutation_detected")
    if cycle.get("task_completed") is not False and work_cycle_id:
        problems.append("work_cycle_task_completion_detected")

    return {
        "runtime_session_id": runtime_session_id,
        "execution_lease_id": execution_lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_binding_id": executor_binding_id,
        "loop_controller_id": loop_controller_id,
        "execution_tick_id": execution_tick_id,
        "work_cycle_id": work_cycle_id,
        "step_request_type": step_request_type,
        "cycle_status": cycle_status,
        "cycle_decision": cycle_decision,
        "recovery_required": recovery_required,
        "expired_or_revoked_upstream": expired_or_revoked,
        "problems": list(dict.fromkeys(problems)),
    }


def validate_runtime_step_executor_bridge_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    evaluation = _evaluate_runtime_step_executor_bridge_request(record)
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

    if evaluation["cycle_status"] == "denied" or "boundary_unlock_attempt" in problems:
        status = "denied"
        next_step_intent = "deny_step_executor_bridge"
    elif evaluation["expired_or_revoked_upstream"]:
        status = "blocked"
        next_step_intent = "wait_for_valid_runtime_authority_chain"
    elif evaluation["cycle_status"] == "stopped":
        status = "blocked"
        next_step_intent = "stop_before_step_executor_bridge"
    elif evaluation["cycle_status"] == "recovery_required" or evaluation["recovery_required"]:
        status = "blocked"
        next_step_intent = "route_to_recovery_step_bridge"
    elif problems:
        status = "blocked"
        next_step_intent = "wait_for_coordinated_work_cycle"
    else:
        status = "bridged"
        next_step_intent = record.get(
            "next_step_intent", "prepare_step_executor_request_record"
        )

    return {
        "schema": RUNTIME_STEP_EXECUTOR_BRIDGE_SCHEMA,
        "valid": not problems and status == "bridged",
        "step_bridge_request_id": record.get("step_bridge_request_id"),
        "bridge_status": status,
        "next_step_intent": next_step_intent,
        "denial_reason": "none" if not problems else ";".join(problems),
        "problems": problems,
        "missing_required_fields": missing,
        "unlock_attempts": unlocks,
        "step_executed": False,
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "filesystem_read_performed": False,
        "filesystem_write_performed": False,
        "filesystem_mutation_performed": False,
        "state_mutation_performed": False,
        "task_completed": False,
        "autonomy_loop_started": False,
        "self_start_performed": False,
        "background_worker_started": False,
        **evaluation,
    }


def _step_request_record(validation: dict[str, Any], step_request_id: str) -> dict[str, Any]:
    return {
        "step_request_id": step_request_id,
        "step_request_type": validation.get("step_request_type"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "work_cycle_id": validation.get("work_cycle_id"),
        "execution_tick_id": validation.get("execution_tick_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "request_mode": "record_only",
        "step_execution_allowed": False,
        "executor_run_allowed": False,
        "task_execution_allowed": False,
        "tool_invocation_allowed": False,
        "filesystem_mutation_allowed": False,
        "state_mutation_allowed": False,
        "task_completion_allowed": False,
        "autonomy_loop_allowed": False,
        "self_start_allowed": False,
        "background_worker_allowed": False,
    }


def build_runtime_step_executor_bridge_record(request: dict[str, Any]) -> dict[str, Any]:
    validation = validate_runtime_step_executor_bridge_request(request)
    record = _as_mapping(request)
    bridge_id = _step_bridge_id(
        request_id=str(validation.get("step_bridge_request_id") or "missing-request"),
        runtime_session_id=str(validation.get("runtime_session_id") or "missing-session"),
        work_cycle_id=str(validation.get("work_cycle_id") or "missing-cycle"),
        execution_tick_id=str(validation.get("execution_tick_id") or "missing-tick"),
        executor_binding_id=str(validation.get("executor_binding_id") or "missing-binding"),
        step_request_type=str(validation.get("step_request_type") or "missing-step-type"),
    )
    step_request_id = _step_request_id(
        runtime_session_id=str(validation.get("runtime_session_id") or "missing-session"),
        work_cycle_id=str(validation.get("work_cycle_id") or "missing-cycle"),
        execution_tick_id=str(validation.get("execution_tick_id") or "missing-tick"),
        executor_binding_id=str(validation.get("executor_binding_id") or "missing-binding"),
        step_request_type=str(validation.get("step_request_type") or "missing-step-type"),
    )
    bridge = {
        "schema": RUNTIME_STEP_EXECUTOR_BRIDGE_SCHEMA,
        "step_bridge_id": bridge_id,
        "step_bridge_request_id": validation.get("step_bridge_request_id"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "loop_controller_id": validation.get("loop_controller_id"),
        "execution_tick_id": validation.get("execution_tick_id"),
        "work_cycle_id": validation.get("work_cycle_id"),
        "step_request_id": step_request_id,
        "step_request_type": validation.get("step_request_type"),
        "step_request": _step_request_record(validation, step_request_id),
        "bridge_status": validation["bridge_status"],
        "next_step_intent": validation["next_step_intent"],
        "denial_reason": validation["denial_reason"],
        "bridge_reason": record.get("bridge_reason"),
        "bridge_time": record.get("bridge_time"),
        "supported_statuses": list(STEP_BRIDGE_STATUSES),
        "supported_step_request_types": list(STEP_REQUEST_TYPES),
        "record_only": True,
        "bridge_only": True,
        "step_executed": False,
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "filesystem_read_performed": False,
        "filesystem_write_performed": False,
        "filesystem_mutation_performed": False,
        "state_mutation_performed": False,
        "task_completed": False,
        "autonomy_loop_started": False,
        "self_start_performed": False,
        "background_worker_started": False,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }
    bridge["audit_projection"] = build_runtime_step_executor_bridge_audit_projection(
        bridge
    )
    return bridge


def build_runtime_step_executor_bridge_audit_projection(
    bridge_record: dict[str, Any] | None,
) -> dict[str, Any]:
    bridge = _as_mapping(bridge_record)
    return {
        "projection": "runtime_step_executor_bridge_audit",
        "projection_only": True,
        "step_bridge_id": bridge.get("step_bridge_id"),
        "runtime_session_id": bridge.get("runtime_session_id"),
        "work_cycle_id": bridge.get("work_cycle_id"),
        "execution_tick_id": bridge.get("execution_tick_id"),
        "executor_binding_id": bridge.get("executor_binding_id"),
        "step_request_id": bridge.get("step_request_id"),
        "step_request_type": bridge.get("step_request_type"),
        "bridge_status": bridge.get("bridge_status", "denied"),
        "next_step_intent": bridge.get("next_step_intent"),
        "denial_reason": bridge.get("denial_reason", "not_evaluated"),
        "step_request": _as_mapping(bridge.get("step_request")),
        "bridged_record_only": bridge.get("bridge_status") == "bridged",
        "bridge_only": True,
        "step_executed": False,
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "filesystem_read_performed": False,
        "filesystem_write_performed": False,
        "filesystem_mutation_performed": False,
        "state_mutation_performed": False,
        "task_completed": False,
        "autonomy_loop_started": False,
        "self_start_performed": False,
        "background_worker_started": False,
    }


def can_runtime_step_executor_bridge_execute(
    bridge_record: dict[str, Any],
) -> dict[str, Any]:
    bridge = _as_mapping(bridge_record)
    return {
        "step_bridge_id": bridge.get("step_bridge_id"),
        "step_request_id": bridge.get("step_request_id"),
        "bridge_status": bridge.get("bridge_status", "denied"),
        "can_create_step_request": bridge.get("bridge_status") == "bridged",
        "can_execute_step": False,
        "can_run_executor": False,
        "can_execute_task": False,
        "can_invoke_tools": False,
        "can_mutate_filesystem": False,
        "can_complete_task": False,
        "can_start_background_loop": False,
        "blocked_reason": "runtime_step_executor_bridge_execution_disabled",
    }


def build_runtime_step_executor_bridge_audit_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_runtime_step_executor_bridge_request(request)
    bridge = build_runtime_step_executor_bridge_record(request)
    return {
        "audit_schema": RUNTIME_STEP_EXECUTOR_BRIDGE_SCHEMA + ".audit",
        "decision": "reserved_runtime_step_executor_bridge_record_only",
        "step_bridge_request_id": validation.get("step_bridge_request_id"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "loop_controller_id": validation.get("loop_controller_id"),
        "execution_tick_id": validation.get("execution_tick_id"),
        "work_cycle_id": validation.get("work_cycle_id"),
        "request_valid": validation["valid"],
        "runtime_step_executor_bridge_record": bridge,
        "audit_projection": bridge["audit_projection"],
        "step_executed": False,
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "filesystem_mutation_performed": False,
        "task_completed": False,
        "autonomy_loop_started": False,
        "self_start_performed": False,
        "background_worker_started": False,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
        "non_mainline_issues": validation["problems"],
    }


def build_runtime_step_executor_bridge_milestone_seal(
    request: dict[str, Any],
) -> dict[str, Any]:
    audit = build_runtime_step_executor_bridge_audit_record(request)
    bridge = _as_mapping(audit.get("runtime_step_executor_bridge_record"))
    return {
        "seal": "runtime_step_executor_bridge_bundle",
        "schema": RUNTIME_STEP_EXECUTOR_BRIDGE_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_RUNTIME_STEP_EXECUTOR_BRIDGE_RECORDS_ONLY",
        "step_bridge_id": bridge.get("step_bridge_id"),
        "step_request_id": bridge.get("step_request_id"),
        "work_cycle_id": bridge.get("work_cycle_id"),
        "execution_tick_id": bridge.get("execution_tick_id"),
        "executor_binding_id": bridge.get("executor_binding_id"),
        "bridge_status": bridge.get("bridge_status"),
        "audit_decision": audit["decision"],
        "bridge_only": True,
        "step_executed": False,
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "filesystem_mutation_performed": False,
        "task_completed": False,
        "autonomy_loop_started": False,
        "self_start_performed": False,
        "background_worker_started": False,
        "forbidden_surfaces_locked": True,
        "audit_required": True,
    }


__all__ = [
    "RUNTIME_STEP_EXECUTOR_BRIDGE_SCHEMA",
    "STEP_BRIDGE_STATUSES",
    "STEP_REQUEST_TYPES",
    "REQUIRED_STEP_BRIDGE_FIELDS",
    "STEP_BRIDGE_LOCKS",
    "build_runtime_step_executor_bridge_request",
    "validate_runtime_step_executor_bridge_request",
    "build_runtime_step_executor_bridge_record",
    "build_runtime_step_executor_bridge_audit_projection",
    "can_runtime_step_executor_bridge_execute",
    "build_runtime_step_executor_bridge_audit_record",
    "build_runtime_step_executor_bridge_milestone_seal",
]
