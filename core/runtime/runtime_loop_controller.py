from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_LOOP_CONTROLLER_SCHEMA = "zero.runtime.loop_controller.v1"

LOOP_CONTROLLER_STATUSES = ("controlled", "denied", "paused", "stopped", "expired", "revoked")

REQUIRED_LOOP_CONTROLLER_FIELDS = (
    "loop_controller_request_id",
    "execution_tick",
    "runtime_session_id",
    "execution_lease",
    "capability_grant",
    "executor_binding",
    "loop_authorization",
    "audit_required",
)

LOOP_CONTROLLER_LOCKS = {
    "record_only": True,
    "single_tick_input_only": True,
    "automatic_next_tick_allowed": False,
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
    return [field for field in REQUIRED_LOOP_CONTROLLER_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in LOOP_CONTROLLER_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _loop_controller_id(
    *,
    request_id: str,
    execution_tick_id: str,
    executor_invocation_id: str,
    runtime_session_id: str,
) -> str:
    fragment = _stable_fragment(
        {
            "request_id": request_id,
            "execution_tick_id": execution_tick_id,
            "executor_invocation_id": executor_invocation_id,
            "runtime_session_id": runtime_session_id,
        }
    )
    return f"runtime-loop-controller::{runtime_session_id}::{execution_tick_id}::{fragment}"


def build_runtime_loop_controller_request(
    *,
    loop_controller_request_id: str,
    execution_tick: dict[str, Any] | None = None,
    runtime_session_id: str | None = None,
    execution_lease: dict[str, Any] | None = None,
    capability_grant: dict[str, Any] | None = None,
    executor_binding: dict[str, Any] | None = None,
    loop_authorization: bool = False,
    loop_reason: str = "explicit_runtime_loop_controller_authorization",
    loop_time: str = "deterministic-time::1353",
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_LOOP_CONTROLLER_SCHEMA,
        "loop_controller_request_id": loop_controller_request_id,
        "execution_tick": _as_mapping(execution_tick),
        "runtime_session_id": runtime_session_id,
        "execution_lease": _as_mapping(execution_lease),
        "capability_grant": _as_mapping(capability_grant),
        "executor_binding": _as_mapping(executor_binding),
        "loop_authorization": loop_authorization,
        "loop_reason": loop_reason,
        "loop_time": loop_time,
        "boundary_locks": deepcopy(LOOP_CONTROLLER_LOCKS),
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


def _evaluate_runtime_loop_controller_request(record: dict[str, Any]) -> dict[str, Any]:
    tick = _as_mapping(record.get("execution_tick"))
    lease = _as_mapping(record.get("execution_lease"))
    grant = _as_mapping(record.get("capability_grant"))
    binding = _as_mapping(record.get("executor_binding"))
    tick_decision = _as_mapping(tick.get("tick_decision"))

    runtime_session_id = record.get("runtime_session_id")
    execution_tick_id = tick.get("execution_tick_id")
    executor_invocation_id = tick.get("executor_invocation_id")
    dispatch_commit_id = tick.get("dispatch_commit_id")
    dispatch_id = tick.get("dispatch_id")
    task_admission_id = tick.get("task_admission_id")
    execution_lease_id = lease.get("lease_id") or tick.get("execution_lease_id")
    capability_grant_id = grant.get("capability_grant_id") or tick.get("capability_grant_id")
    executor_binding_id = binding.get("executor_binding_id") or tick.get("executor_binding_id")

    ticked = (
        bool(execution_tick_id)
        and tick.get("tick_status") == "ticked"
        and tick.get("tick_ready") is True
        and tick.get("record_only") is True
        and tick.get("single_cycle_only") is True
        and tick.get("continuation_allowed") is False
        and tick.get("executor_run_performed") is False
        and tick.get("task_execution_performed") is False
        and tick.get("tool_invoked") is False
        and tick.get("state_mutation_performed") is False
        and tick.get("task_completed") is False
        and tick.get("autonomy_loop_started") is False
        and tick.get("background_worker_started") is False
    )
    active_lease = (
        bool(execution_lease_id)
        and lease.get("lease_id") == execution_lease_id
        and lease.get("runtime_session_id") == runtime_session_id
        and lease.get("lease_status") == "granted"
    )
    active_grant = (
        bool(capability_grant_id)
        and grant.get("capability_grant_id") == capability_grant_id
        and grant.get("owner_session_id") == runtime_session_id
        and grant.get("owner_lease_id") == execution_lease_id
        and grant.get("grant_status") == "granted"
    )
    active_binding = (
        bool(executor_binding_id)
        and binding.get("executor_binding_id") == executor_binding_id
        and binding.get("runtime_session_id") == runtime_session_id
        and binding.get("execution_lease_id") == execution_lease_id
        and binding.get("capability_grant_id") == capability_grant_id
        and binding.get("binding_status") == "bound"
    )
    tick_decision_locked = (
        bool(tick_decision)
        and tick_decision.get("single_cycle_only") is True
        and tick_decision.get("continuation_allowed") is False
        and tick_decision.get("executor_run_allowed") is False
        and tick_decision.get("task_execution_allowed") is False
        and tick_decision.get("tool_invocation_allowed") is False
        and tick_decision.get("state_mutation_allowed") is False
        and tick_decision.get("autonomy_loop_allowed") is False
        and tick_decision.get("background_worker_allowed") is False
    )

    problems: list[str] = []
    if not execution_tick_id:
        problems.append("missing_execution_tick")
    elif not ticked:
        problems.append("execution_tick_not_ticked")
    if tick.get("tick_status") == "denied":
        problems.append("denied_execution_tick")
    if tick.get("tick_status") == "expired":
        problems.append("expired_execution_tick")
    if tick.get("tick_status") == "revoked":
        problems.append("revoked_execution_tick")
    if not runtime_session_id:
        problems.append("invalid_runtime_session_id")
    if tick and tick.get("runtime_session_id") != runtime_session_id:
        problems.append("execution_tick_session_mismatch")
    if tick and tick.get("execution_lease_id") != execution_lease_id:
        problems.append("execution_tick_lease_mismatch")
    if tick and tick.get("capability_grant_id") != capability_grant_id:
        problems.append("execution_tick_capability_mismatch")
    if tick and tick.get("executor_binding_id") != executor_binding_id:
        problems.append("execution_tick_binding_mismatch")
    if not active_lease:
        problems.append("inactive_execution_lease")
    if lease.get("lease_status") == "expired":
        problems.append("expired_execution_lease")
    if lease.get("lease_status") == "revoked":
        problems.append("revoked_execution_lease")
    if not active_grant:
        problems.append("inactive_capability_grant")
    if grant.get("grant_status") == "revoked":
        problems.append("revoked_capability_grant")
    if grant.get("grant_status") == "expired":
        problems.append("expired_capability_grant")
    if not active_binding:
        problems.append("inactive_executor_binding")
    if binding.get("binding_status") == "revoked":
        problems.append("revoked_executor_binding")
    if binding.get("binding_status") == "expired":
        problems.append("expired_executor_binding")
    if not tick_decision_locked:
        problems.append("execution_tick_decision_unlocked")
    if record.get("loop_authorization") is not True:
        problems.append("loop_not_authorized")

    return {
        "execution_tick_id": execution_tick_id,
        "executor_invocation_id": executor_invocation_id,
        "dispatch_commit_id": dispatch_commit_id,
        "dispatch_id": dispatch_id,
        "task_admission_id": task_admission_id,
        "runtime_session_id": runtime_session_id,
        "execution_lease_id": execution_lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_binding_id": executor_binding_id,
        "problems": problems,
    }


def validate_runtime_loop_controller_request(request: dict[str, Any]) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    evaluation = _evaluate_runtime_loop_controller_request(record)

    problems = list(missing) + list(unlocks) + list(evaluation["problems"])
    status = "controlled" if not problems else "denied"

    return {
        "schema": RUNTIME_LOOP_CONTROLLER_SCHEMA,
        "loop_controller_request_id": record.get("loop_controller_request_id"),
        "valid": not problems,
        "loop_status": status,
        "denial_reason": "none" if not problems else ";".join(problems),
        "problems": problems,
        "missing_required_fields": missing,
        "unlock_attempts": unlocks,
        "audit_required": record.get("audit_required") is True,
        "non_mainline_issue_reporting_required": record.get("non_mainline_issue_reporting_required") is True,
        **evaluation,
    }


def _loop_decision(validation: dict[str, Any]) -> dict[str, Any]:
    controlled = validation.get("loop_status") == "controlled"
    return {
        "loop_controller_mode": "single_cycle_governor_record_only",
        "controlled": controlled,
        "next_tick_may_be_requested": controlled,
        "automatic_next_tick_allowed": False,
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
        "denial_reason": validation.get("denial_reason", "not_evaluated"),
    }


def build_runtime_loop_controller_record(request: dict[str, Any]) -> dict[str, Any]:
    record = _as_mapping(request)
    validation = validate_runtime_loop_controller_request(record)
    loop_status = validation["loop_status"]
    loop_controller_id = _loop_controller_id(
        request_id=str(validation.get("loop_controller_request_id") or "missing-request"),
        execution_tick_id=str(validation.get("execution_tick_id") or "missing-tick"),
        executor_invocation_id=str(validation.get("executor_invocation_id") or "missing-invocation"),
        runtime_session_id=str(validation.get("runtime_session_id") or "missing-session"),
    )
    decision = _loop_decision(validation)

    loop_record = {
        "schema": RUNTIME_LOOP_CONTROLLER_SCHEMA,
        "loop_controller_id": loop_controller_id,
        "loop_controller_request_id": validation.get("loop_controller_request_id"),
        "execution_tick_id": validation.get("execution_tick_id"),
        "executor_invocation_id": validation.get("executor_invocation_id"),
        "dispatch_commit_id": validation.get("dispatch_commit_id"),
        "dispatch_id": validation.get("dispatch_id"),
        "task_admission_id": validation.get("task_admission_id"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "loop_status": loop_status,
        "loop_ready": loop_status == "controlled",
        "denial_reason": validation["denial_reason"],
        "loop_reason": record.get("loop_reason"),
        "loop_time": record.get("loop_time"),
        "loop_decision": decision,
        "record_only": True,
        "single_cycle_governor_only": True,
        "automatic_next_tick_allowed": False,
        "next_tick_started": False,
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
    loop_record["audit_record"] = build_runtime_loop_controller_audit_projection(loop_record)
    return loop_record


def pause_runtime_loop_controller(loop_record: dict[str, Any]) -> dict[str, Any]:
    record = _as_mapping(loop_record)
    record["loop_status"] = "paused"
    record["loop_ready"] = False
    record["denial_reason"] = "runtime_loop_controller_paused"
    record["automatic_next_tick_allowed"] = False
    record["next_tick_started"] = False
    record["audit_record"] = build_runtime_loop_controller_audit_projection(record)
    return record


def stop_runtime_loop_controller(loop_record: dict[str, Any]) -> dict[str, Any]:
    record = _as_mapping(loop_record)
    record["loop_status"] = "stopped"
    record["loop_ready"] = False
    record["denial_reason"] = "runtime_loop_controller_stopped"
    record["automatic_next_tick_allowed"] = False
    record["next_tick_started"] = False
    record["audit_record"] = build_runtime_loop_controller_audit_projection(record)
    return record


def expire_runtime_loop_controller(loop_record: dict[str, Any]) -> dict[str, Any]:
    record = _as_mapping(loop_record)
    record["loop_status"] = "expired"
    record["loop_ready"] = False
    record["denial_reason"] = "runtime_loop_controller_expired"
    record["automatic_next_tick_allowed"] = False
    record["next_tick_started"] = False
    record["audit_record"] = build_runtime_loop_controller_audit_projection(record)
    return record


def revoke_runtime_loop_controller(loop_record: dict[str, Any]) -> dict[str, Any]:
    record = _as_mapping(loop_record)
    record["loop_status"] = "revoked"
    record["loop_ready"] = False
    record["denial_reason"] = "runtime_loop_controller_revoked"
    record["automatic_next_tick_allowed"] = False
    record["next_tick_started"] = False
    record["audit_record"] = build_runtime_loop_controller_audit_projection(record)
    return record


def can_runtime_loop_controller_continue(loop_record: dict[str, Any]) -> dict[str, Any]:
    record = _as_mapping(loop_record)
    controlled = record.get("loop_status") == "controlled" and record.get("loop_ready") is True
    return {
        "can_continue": False,
        "can_request_next_tick": controlled,
        "can_start_background_loop": False,
        "can_self_start": False,
        "can_run_executor": False,
        "can_execute_task": False,
        "blocked_reason": "runtime_loop_background_execution_disabled",
        "loop_controller_id": record.get("loop_controller_id"),
        "loop_status": record.get("loop_status", "denied"),
    }


def build_runtime_loop_controller_audit_projection(
    loop_record: dict[str, Any],
) -> dict[str, Any]:
    loop = _as_mapping(loop_record)
    return {
        "projection": "runtime_loop_controller_audit",
        "projection_only": True,
        "loop_controller_id": loop.get("loop_controller_id"),
        "execution_tick_id": loop.get("execution_tick_id"),
        "executor_invocation_id": loop.get("executor_invocation_id"),
        "dispatch_commit_id": loop.get("dispatch_commit_id"),
        "dispatch_id": loop.get("dispatch_id"),
        "task_admission_id": loop.get("task_admission_id"),
        "executor_binding_id": loop.get("executor_binding_id"),
        "loop_status": loop.get("loop_status", "denied"),
        "denial_reason": loop.get("denial_reason", "not_evaluated"),
        "loop_time": loop.get("loop_time"),
        "loop_decision": _as_mapping(loop.get("loop_decision")),
        "controlled_record_only": loop.get("loop_status") == "controlled",
        "loop_ready": loop.get("loop_status") == "controlled",
        "single_cycle_governor_only": True,
        "automatic_next_tick_allowed": False,
        "next_tick_started": False,
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


def build_runtime_loop_controller_audit_record(request: dict[str, Any]) -> dict[str, Any]:
    validation = validate_runtime_loop_controller_request(request)
    loop = build_runtime_loop_controller_record(request)
    return {
        "audit_schema": RUNTIME_LOOP_CONTROLLER_SCHEMA + ".audit",
        "decision": "reserved_runtime_loop_controller_record_only",
        "loop_controller_request_id": validation.get("loop_controller_request_id"),
        "execution_tick_id": validation.get("execution_tick_id"),
        "executor_invocation_id": validation.get("executor_invocation_id"),
        "dispatch_commit_id": validation.get("dispatch_commit_id"),
        "dispatch_id": validation.get("dispatch_id"),
        "task_admission_id": validation.get("task_admission_id"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "request_valid": validation["valid"],
        "runtime_loop_controller_record": loop,
        "audit_projection": loop["audit_record"],
        "automatic_next_tick_allowed": False,
        "next_tick_started": False,
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


def build_runtime_loop_controller_milestone_seal(request: dict[str, Any]) -> dict[str, Any]:
    audit = build_runtime_loop_controller_audit_record(request)
    loop = _as_mapping(audit.get("runtime_loop_controller_record"))
    return {
        "seal": "runtime_loop_controller_bundle",
        "schema": RUNTIME_LOOP_CONTROLLER_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_RUNTIME_LOOP_CONTROLLER_RECORDS_ONLY_NO_BACKGROUND_LOOP",
        "loop_controller_id": loop.get("loop_controller_id"),
        "execution_tick_id": loop.get("execution_tick_id"),
        "executor_invocation_id": loop.get("executor_invocation_id"),
        "loop_status": loop.get("loop_status"),
        "audit_decision": audit["decision"],
        "single_cycle_governor_only": True,
        "automatic_next_tick_allowed": False,
        "next_tick_started": False,
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
    "RUNTIME_LOOP_CONTROLLER_SCHEMA",
    "LOOP_CONTROLLER_STATUSES",
    "REQUIRED_LOOP_CONTROLLER_FIELDS",
    "LOOP_CONTROLLER_LOCKS",
    "build_runtime_loop_controller_request",
    "validate_runtime_loop_controller_request",
    "build_runtime_loop_controller_record",
    "pause_runtime_loop_controller",
    "stop_runtime_loop_controller",
    "expire_runtime_loop_controller",
    "revoke_runtime_loop_controller",
    "can_runtime_loop_controller_continue",
    "build_runtime_loop_controller_audit_projection",
    "build_runtime_loop_controller_audit_record",
    "build_runtime_loop_controller_milestone_seal",
]
