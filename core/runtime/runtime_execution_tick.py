from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_EXECUTION_TICK_SCHEMA = "zero.runtime.execution_tick.v1"

EXECUTION_TICK_STATUSES = ("ticked", "denied", "expired", "revoked")

REQUIRED_EXECUTION_TICK_FIELDS = (
    "execution_tick_request_id",
    "executor_invocation_boundary",
    "runtime_session_id",
    "execution_lease",
    "capability_grant",
    "executor_binding",
    "tick_authorization",
    "audit_required",
)

EXECUTION_TICK_LOCKS = {
    "single_cycle_only": True,
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
    return [field for field in REQUIRED_EXECUTION_TICK_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in EXECUTION_TICK_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _execution_tick_id(
    *,
    request_id: str,
    executor_invocation_id: str,
    dispatch_commit_id: str,
    executor_binding_id: str,
    runtime_session_id: str,
) -> str:
    fragment = _stable_fragment(
        {
            "request_id": request_id,
            "executor_invocation_id": executor_invocation_id,
            "dispatch_commit_id": dispatch_commit_id,
            "executor_binding_id": executor_binding_id,
            "runtime_session_id": runtime_session_id,
        }
    )
    return (
        f"runtime-execution-tick::{runtime_session_id}::"
        f"{executor_invocation_id}::{fragment}"
    )


def build_runtime_execution_tick_request(
    *,
    execution_tick_request_id: str,
    executor_invocation_boundary: dict[str, Any] | None = None,
    runtime_session_id: str | None = None,
    execution_lease: dict[str, Any] | None = None,
    capability_grant: dict[str, Any] | None = None,
    executor_binding: dict[str, Any] | None = None,
    tick_authorization: bool = False,
    tick_reason: str = "explicit_runtime_execution_tick_authorization",
    tick_time: str = "deterministic-time::1345",
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_EXECUTION_TICK_SCHEMA,
        "execution_tick_request_id": execution_tick_request_id,
        "executor_invocation_boundary": _as_mapping(executor_invocation_boundary),
        "runtime_session_id": runtime_session_id,
        "execution_lease": _as_mapping(execution_lease),
        "capability_grant": _as_mapping(capability_grant),
        "executor_binding": _as_mapping(executor_binding),
        "tick_authorization": tick_authorization,
        "tick_reason": tick_reason,
        "tick_time": tick_time,
        "boundary_locks": deepcopy(EXECUTION_TICK_LOCKS),
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


def _evaluate_runtime_execution_tick_request(record: dict[str, Any]) -> dict[str, Any]:
    boundary = _as_mapping(record.get("executor_invocation_boundary"))
    lease = _as_mapping(record.get("execution_lease"))
    grant = _as_mapping(record.get("capability_grant"))
    binding = _as_mapping(record.get("executor_binding"))
    envelope = _as_mapping(boundary.get("invocation_envelope"))
    executor_target = _as_mapping(boundary.get("executor_target"))

    runtime_session_id = record.get("runtime_session_id")
    executor_invocation_id = boundary.get("executor_invocation_id")
    dispatch_commit_id = boundary.get("dispatch_commit_id")
    dispatch_id = boundary.get("dispatch_id")
    task_admission_id = boundary.get("task_admission_id")
    execution_lease_id = lease.get("lease_id") or boundary.get("execution_lease_id")
    capability_grant_id = grant.get("capability_grant_id") or boundary.get(
        "capability_grant_id"
    )
    executor_binding_id = binding.get("executor_binding_id") or boundary.get(
        "executor_binding_id"
    )

    bounded = (
        bool(executor_invocation_id)
        and boundary.get("invocation_status") == "bounded"
        and boundary.get("boundary_ready") is True
        and boundary.get("record_only") is True
        and boundary.get("executor_run_performed") is False
        and boundary.get("task_execution_performed") is False
        and boundary.get("tool_invoked") is False
        and boundary.get("state_mutation_performed") is False
        and boundary.get("task_completed") is False
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
    envelope_matches = (
        bool(envelope)
        and envelope.get("runtime_session_id") == runtime_session_id
        and envelope.get("dispatch_commit_id") == dispatch_commit_id
        and envelope.get("dispatch_id") == dispatch_id
        and envelope.get("task_admission_id") == task_admission_id
        and envelope.get("executor_binding_id") == executor_binding_id
        and envelope.get("target_mode") == "record_only"
        and envelope.get("executor_run_allowed") is False
        and envelope.get("task_execution_allowed") is False
        and envelope.get("autonomy_loop_allowed") is False
    )
    target_matches = (
        bool(executor_target)
        and executor_target.get("executor_binding_id") == executor_binding_id
        and executor_target.get("runtime_session_id") == runtime_session_id
        and executor_target.get("execution_lease_id") == execution_lease_id
        and executor_target.get("capability_grant_id") == capability_grant_id
        and executor_target.get("target_mode") == "record_only"
    )

    problems: list[str] = []
    if not executor_invocation_id:
        problems.append("missing_executor_invocation_boundary")
    elif not bounded:
        problems.append("executor_invocation_boundary_not_bounded")
    if boundary.get("invocation_status") == "denied":
        problems.append("denied_executor_invocation_boundary")
    if boundary.get("invocation_status") == "expired":
        problems.append("expired_executor_invocation_boundary")
    if boundary.get("invocation_status") == "revoked":
        problems.append("revoked_executor_invocation_boundary")
    if not runtime_session_id:
        problems.append("invalid_runtime_session_id")
    if boundary and boundary.get("runtime_session_id") != runtime_session_id:
        problems.append("executor_invocation_session_mismatch")
    if boundary and boundary.get("execution_lease_id") != execution_lease_id:
        problems.append("executor_invocation_lease_mismatch")
    if boundary and boundary.get("capability_grant_id") != capability_grant_id:
        problems.append("executor_invocation_capability_mismatch")
    if boundary and boundary.get("executor_binding_id") != executor_binding_id:
        problems.append("executor_invocation_binding_mismatch")
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
    if not envelope_matches:
        problems.append("invalid_invocation_envelope")
    if not target_matches:
        problems.append("executor_target_mismatch")
    if record.get("tick_authorization") is not True:
        problems.append("tick_not_authorized")

    return {
        "executor_invocation_id": executor_invocation_id,
        "dispatch_commit_id": dispatch_commit_id,
        "dispatch_id": dispatch_id,
        "task_admission_id": task_admission_id,
        "runtime_session_id": runtime_session_id,
        "execution_lease_id": execution_lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_binding_id": executor_binding_id,
        "executor_target": executor_target,
        "invocation_envelope": envelope,
        "problems": problems,
    }


def validate_runtime_execution_tick_request(request: dict[str, Any]) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    evaluation = _evaluate_runtime_execution_tick_request(record)
    problems = list(dict.fromkeys(evaluation["problems"]))
    if missing:
        problems.append("missing_required_fields")
    if unlocks:
        problems.append("boundary_unlock_attempt")
    if record.get("audit_required") is not True:
        problems.append("audit_not_required")
    if record.get("non_mainline_issue_reporting_required") is not True:
        problems.append("non_mainline_issue_reporting_not_required")

    status = "ticked" if not problems else "denied"
    return {
        "schema": RUNTIME_EXECUTION_TICK_SCHEMA,
        "valid": not problems,
        "execution_tick_request_id": record.get("execution_tick_request_id"),
        "executor_invocation_id": evaluation["executor_invocation_id"],
        "dispatch_commit_id": evaluation["dispatch_commit_id"],
        "dispatch_id": evaluation["dispatch_id"],
        "task_admission_id": evaluation["task_admission_id"],
        "runtime_session_id": evaluation["runtime_session_id"],
        "execution_lease_id": evaluation["execution_lease_id"],
        "capability_grant_id": evaluation["capability_grant_id"],
        "executor_binding_id": evaluation["executor_binding_id"],
        "executor_target": evaluation["executor_target"],
        "invocation_envelope": evaluation["invocation_envelope"],
        "tick_status": status,
        "tick_ready": not problems,
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
    }


def _build_tick_decision(validation: dict[str, Any]) -> dict[str, Any]:
    target = _as_mapping(validation.get("executor_target"))
    return {
        "decision_type": "runtime_execution_tick_single_cycle_record_only",
        "runtime_session_id": validation.get("runtime_session_id"),
        "executor_invocation_id": validation.get("executor_invocation_id"),
        "dispatch_commit_id": validation.get("dispatch_commit_id"),
        "dispatch_id": validation.get("dispatch_id"),
        "task_admission_id": validation.get("task_admission_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "executor_id": target.get("executor_id"),
        "executor_type": target.get("executor_type"),
        "single_cycle_only": True,
        "continuation_allowed": False,
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


def build_runtime_execution_tick_record(request: dict[str, Any]) -> dict[str, Any]:
    validation = validate_runtime_execution_tick_request(request)
    record = _as_mapping(request)
    tick_id = _execution_tick_id(
        request_id=str(validation.get("execution_tick_request_id")),
        executor_invocation_id=str(validation.get("executor_invocation_id")),
        dispatch_commit_id=str(validation.get("dispatch_commit_id")),
        executor_binding_id=str(validation.get("executor_binding_id")),
        runtime_session_id=str(validation.get("runtime_session_id")),
    )
    tick = {
        "execution_tick_id": tick_id,
        "executor_invocation_id": validation.get("executor_invocation_id"),
        "dispatch_commit_id": validation.get("dispatch_commit_id"),
        "dispatch_id": validation.get("dispatch_id"),
        "task_admission_id": validation.get("task_admission_id"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "executor_target": _as_mapping(validation.get("executor_target")),
        "invocation_envelope": _as_mapping(validation.get("invocation_envelope")),
        "tick_decision": _build_tick_decision(validation),
        "tick_status": validation["tick_status"],
        "tick_reason": record.get("tick_reason"),
        "tick_time": record.get("tick_time"),
        "denial_reason": validation["denial_reason"],
        "audit_record": {},
        "supported_statuses": list(EXECUTION_TICK_STATUSES),
        "record_only": True,
        "tick_ready": validation["tick_status"] == "ticked",
        "single_cycle_only": True,
        "continuation_allowed": False,
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
    tick["audit_record"] = build_runtime_execution_tick_audit_projection(tick)
    return tick


def expire_runtime_execution_tick(
    tick_record: dict[str, Any],
    *,
    reason: str = "runtime_execution_tick_expired",
) -> dict[str, Any]:
    tick = _as_mapping(tick_record)
    tick["tick_status"] = "expired"
    tick["tick_ready"] = False
    tick["continuation_allowed"] = False
    tick["denial_reason"] = reason
    tick["executor_run_performed"] = False
    tick["task_execution_performed"] = False
    tick["audit_record"] = build_runtime_execution_tick_audit_projection(tick)
    return tick


def revoke_runtime_execution_tick(
    tick_record: dict[str, Any],
    *,
    reason: str = "runtime_execution_tick_revoked",
) -> dict[str, Any]:
    tick = _as_mapping(tick_record)
    tick["tick_status"] = "revoked"
    tick["tick_ready"] = False
    tick["continuation_allowed"] = False
    tick["denial_reason"] = reason
    tick["executor_run_performed"] = False
    tick["task_execution_performed"] = False
    tick["audit_record"] = build_runtime_execution_tick_audit_projection(tick)
    return tick


def can_runtime_execution_tick_continue(tick_record: dict[str, Any]) -> dict[str, Any]:
    tick = _as_mapping(tick_record)
    return {
        "execution_tick_id": tick.get("execution_tick_id"),
        "executor_invocation_id": tick.get("executor_invocation_id"),
        "tick_status": tick.get("tick_status", "denied"),
        "can_continue": False,
        "can_run_executor": False,
        "can_execute_task": False,
        "blocked": True,
        "blocked_reason": "runtime_execution_tick_continuation_disabled",
        "single_cycle_only": True,
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


def build_runtime_execution_tick_audit_projection(
    tick_record: dict[str, Any] | None,
) -> dict[str, Any]:
    tick = _as_mapping(tick_record)
    return {
        "projection": "runtime_execution_tick_audit",
        "projection_only": True,
        "execution_tick_id": tick.get("execution_tick_id"),
        "executor_invocation_id": tick.get("executor_invocation_id"),
        "dispatch_commit_id": tick.get("dispatch_commit_id"),
        "dispatch_id": tick.get("dispatch_id"),
        "task_admission_id": tick.get("task_admission_id"),
        "executor_binding_id": tick.get("executor_binding_id"),
        "tick_status": tick.get("tick_status", "denied"),
        "denial_reason": tick.get("denial_reason", "not_evaluated"),
        "tick_time": tick.get("tick_time"),
        "executor_target": _as_mapping(tick.get("executor_target")),
        "tick_decision": _as_mapping(tick.get("tick_decision")),
        "ticked_record_only": tick.get("tick_status") == "ticked",
        "tick_ready": tick.get("tick_status") == "ticked",
        "single_cycle_only": True,
        "continuation_allowed": False,
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


def build_runtime_execution_tick_audit_record(request: dict[str, Any]) -> dict[str, Any]:
    validation = validate_runtime_execution_tick_request(request)
    tick = build_runtime_execution_tick_record(request)
    return {
        "audit_schema": RUNTIME_EXECUTION_TICK_SCHEMA + ".audit",
        "decision": "reserved_runtime_execution_tick_record_only",
        "execution_tick_request_id": validation.get("execution_tick_request_id"),
        "executor_invocation_id": validation.get("executor_invocation_id"),
        "dispatch_commit_id": validation.get("dispatch_commit_id"),
        "dispatch_id": validation.get("dispatch_id"),
        "task_admission_id": validation.get("task_admission_id"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "request_valid": validation["valid"],
        "runtime_execution_tick_record": tick,
        "audit_projection": tick["audit_record"],
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


def build_runtime_execution_tick_milestone_seal(request: dict[str, Any]) -> dict[str, Any]:
    audit = build_runtime_execution_tick_audit_record(request)
    tick = _as_mapping(audit.get("runtime_execution_tick_record"))
    return {
        "seal": "runtime_execution_tick_bundle",
        "schema": RUNTIME_EXECUTION_TICK_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_RUNTIME_EXECUTION_TICK_RECORDS_ONLY_NO_EXECUTION",
        "execution_tick_id": tick.get("execution_tick_id"),
        "executor_invocation_id": tick.get("executor_invocation_id"),
        "dispatch_commit_id": tick.get("dispatch_commit_id"),
        "dispatch_id": tick.get("dispatch_id"),
        "task_admission_id": tick.get("task_admission_id"),
        "tick_status": tick.get("tick_status"),
        "audit_decision": audit["decision"],
        "single_cycle_only": True,
        "continuation_allowed": False,
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
    "RUNTIME_EXECUTION_TICK_SCHEMA",
    "EXECUTION_TICK_STATUSES",
    "REQUIRED_EXECUTION_TICK_FIELDS",
    "EXECUTION_TICK_LOCKS",
    "build_runtime_execution_tick_request",
    "validate_runtime_execution_tick_request",
    "build_runtime_execution_tick_record",
    "expire_runtime_execution_tick",
    "revoke_runtime_execution_tick",
    "can_runtime_execution_tick_continue",
    "build_runtime_execution_tick_audit_projection",
    "build_runtime_execution_tick_audit_record",
    "build_runtime_execution_tick_milestone_seal",
]
