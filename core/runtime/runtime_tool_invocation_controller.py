from __future__ import annotations

from copy import deepcopy
from typing import Any


RUNTIME_TOOL_INVOCATION_CONTROLLER_SCHEMA = (
    "zero.runtime.tool_invocation_controller.v1"
)

AUTHORIZED_TOOL_INVOCATION_DECISION = "AUTHORIZE_TOOL_INVOCATION_RECORD_ONLY"

TOOL_INVOCATION_STATES = (
    "pending",
    "approved",
    "completed",
    "failed",
    "revoked",
    "expired",
)

REQUIRED_TOOL_INVOCATION_FIELDS = (
    "tool_invocation_request_id",
    "runtime_session_id",
    "execution_lease",
    "capability_grant",
    "executor_binding",
    "tool_boundary",
    "authorization_input",
    "timeout_model",
    "cancellation_model",
    "failure_ownership",
    "audit_required",
)

TOOL_INVOCATION_LOCKS = {
    "actual_tool_execution_allowed": False,
    "subprocess_allowed": False,
    "shell_allowed": False,
    "filesystem_access_allowed": False,
    "network_allowed": False,
    "mutation_allowed": False,
    "task_execution_allowed": False,
    "autonomy_allowed": False,
    "background_loop_allowed": False,
}

REQUIRED_BLOCKERS = (
    "runtime_session_id_required",
    "active_execution_lease_required",
    "active_capability_grant_required",
    "active_executor_binding_required",
    "admitted_tool_boundary_required",
    "explicit_invocation_authorization_required",
    "invocation_record_only",
    "synthetic_result_only",
    "actual_tool_execution_locked",
    "subprocess_locked",
    "shell_locked",
    "filesystem_access_locked",
    "network_locked",
    "mutation_locked",
    "task_execution_locked",
    "autonomy_locked",
    "background_loop_locked",
)


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _missing_required_fields(record: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_TOOL_INVOCATION_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in TOOL_INVOCATION_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def _tool_invocation_id(
    request_id: str,
    session_id: str,
    lease_id: str,
    capability_grant_id: str,
    executor_binding_id: str,
    tool_boundary_id: str,
    tool_name: str,
) -> str:
    return (
        f"tool-invocation::{session_id}::{lease_id}::{capability_grant_id}::"
        f"{executor_binding_id}::{tool_boundary_id}::{tool_name}::{request_id}"
    )


def build_runtime_tool_invocation_request(
    *,
    tool_invocation_request_id: str,
    runtime_session_id: str | None = None,
    execution_lease: dict[str, Any] | None = None,
    capability_grant: dict[str, Any] | None = None,
    executor_binding: dict[str, Any] | None = None,
    tool_boundary: dict[str, Any] | None = None,
    authorization_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_TOOL_INVOCATION_CONTROLLER_SCHEMA,
        "tool_invocation_request_id": tool_invocation_request_id,
        "runtime_session_id": runtime_session_id,
        "execution_lease": (
            deepcopy(execution_lease) if execution_lease is not None else {}
        ),
        "capability_grant": (
            deepcopy(capability_grant) if capability_grant is not None else {}
        ),
        "executor_binding": (
            deepcopy(executor_binding) if executor_binding is not None else {}
        ),
        "tool_boundary": deepcopy(tool_boundary) if tool_boundary is not None else {},
        "authorization_input": (
            deepcopy(authorization_input)
            if authorization_input is not None
            else {
                "decision": "NO_GO",
                "explicit_invocation_authorization": False,
                "authorize_tool_invocation_record": False,
            }
        ),
        "timeout_model": {
            "model": "deterministic_counter",
            "timeout_at_tick": 1,
            "current_tick": 0,
            "timed_out": False,
        },
        "cancellation_model": {
            "cancellable": True,
            "cancelled": False,
            "cancellation_reason": None,
        },
        "failure_ownership": {
            "failure_owner": "runtime_tool_invocation_controller",
            "failure_recorded": False,
            "failure_reason": None,
        },
        "boundary_locks": deepcopy(TOOL_INVOCATION_LOCKS),
        "audit_required": True,
        "blockers": list(REQUIRED_BLOCKERS),
        "non_mainline_issue_reporting_required": True,
    }


def _evaluate_invocation_request(record: dict[str, Any]) -> dict[str, Any]:
    session_id = record.get("runtime_session_id")
    lease = _as_mapping(record.get("execution_lease"))
    grant = _as_mapping(record.get("capability_grant"))
    binding = _as_mapping(record.get("executor_binding"))
    boundary = _as_mapping(record.get("tool_boundary"))
    authorization = _as_mapping(record.get("authorization_input"))

    lease_id = lease.get("lease_id")
    capability_grant_id = grant.get("capability_grant_id")
    executor_binding_id = binding.get("executor_binding_id")
    tool_boundary_id = boundary.get("tool_boundary_id")
    tool_name = boundary.get("requested_tool_name")

    active_lease = (
        bool(lease_id)
        and lease.get("runtime_session_id") == session_id
        and lease.get("lease_status") == "granted"
    )
    active_grant = (
        bool(capability_grant_id)
        and grant.get("owner_session_id") == session_id
        and grant.get("owner_lease_id") == lease_id
        and grant.get("grant_status") == "granted"
    )
    active_binding = (
        bool(executor_binding_id)
        and binding.get("runtime_session_id") == session_id
        and binding.get("execution_lease_id") == lease_id
        and binding.get("capability_grant_id") == capability_grant_id
        and binding.get("binding_status") == "bound"
    )
    admitted_boundary = (
        bool(tool_boundary_id)
        and boundary.get("runtime_session_id") == session_id
        and boundary.get("execution_lease_id") == lease_id
        and boundary.get("capability_grant_id") == capability_grant_id
        and boundary.get("executor_binding_id") == executor_binding_id
        and boundary.get("tool_boundary_status") == "admitted"
        and boundary.get("admission_granted") is True
    )
    authorized = (
        authorization.get("decision") == AUTHORIZED_TOOL_INVOCATION_DECISION
        and authorization.get("explicit_invocation_authorization") is True
        and authorization.get("authorize_tool_invocation_record") is True
    )

    problems: list[str] = []
    if not session_id:
        problems.append("invalid_runtime_session_id")
    if not active_lease:
        problems.append("inactive_execution_lease")
    if not active_grant:
        problems.append("inactive_capability_grant")
    if not active_binding:
        problems.append("inactive_executor_binding")
    if not tool_boundary_id:
        problems.append("missing_tool_boundary")
    elif not admitted_boundary:
        problems.append("tool_boundary_not_admitted")
    if not tool_name:
        problems.append("invalid_tool_name")
    if not authorized:
        problems.append("tool_invocation_authorization_missing")

    return {
        "runtime_session_id": session_id,
        "execution_lease_id": lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_binding_id": executor_binding_id,
        "tool_boundary_id": tool_boundary_id,
        "tool_name": tool_name,
        "authorized": authorized,
        "problems": problems,
    }


def validate_runtime_tool_invocation_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    blockers = _as_list(record.get("blockers"))
    missing_blockers = [b for b in REQUIRED_BLOCKERS if b not in blockers]
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    evaluation = _evaluate_invocation_request(record)

    problems = list(evaluation["problems"])
    if missing:
        problems.append("missing_required_fields")
    if missing_blockers:
        problems.append("missing_required_blockers")
    if unlocks:
        problems.append("boundary_unlock_attempt")
    if record.get("audit_required") is not True:
        problems.append("audit_not_required")
    if record.get("non_mainline_issue_reporting_required") is not True:
        problems.append("non_mainline_issue_reporting_not_required")

    invocation_record = (
        build_runtime_tool_invocation_record(record)
        if not problems
        else None
    )

    return {
        "schema": RUNTIME_TOOL_INVOCATION_CONTROLLER_SCHEMA,
        "valid": not problems,
        "tool_invocation_request_id": record.get("tool_invocation_request_id"),
        "runtime_session_id": evaluation["runtime_session_id"],
        "execution_lease_id": evaluation["execution_lease_id"],
        "capability_grant_id": evaluation["capability_grant_id"],
        "executor_binding_id": evaluation["executor_binding_id"],
        "tool_boundary_id": evaluation["tool_boundary_id"],
        "status": "accepted_tool_invocation_record_request"
        if not problems
        else "blocked",
        "problems": problems,
        "missing_required_fields": missing,
        "missing_required_blockers": missing_blockers,
        "unlock_attempts": unlocks,
        "invocation_created": invocation_record is not None,
        "tool_invocation_record": invocation_record,
        "actual_tool_executed": False,
        "subprocess_started": False,
        "shell_started": False,
        "filesystem_access_performed": False,
        "network_performed": False,
        "mutation_performed": False,
        "task_executed": False,
        "autonomy_started": False,
        "background_loop_started": False,
        "audit_required": True,
    }


def build_runtime_tool_invocation_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    evaluation = _evaluate_invocation_request(record)
    session_id = str(evaluation["runtime_session_id"])
    lease_id = str(evaluation["execution_lease_id"])
    capability_grant_id = str(evaluation["capability_grant_id"])
    executor_binding_id = str(evaluation["executor_binding_id"])
    tool_boundary_id = str(evaluation["tool_boundary_id"])
    tool_name = str(evaluation["tool_name"])
    request_id = str(record.get("tool_invocation_request_id"))
    invocation_id = _tool_invocation_id(
        request_id,
        session_id,
        lease_id,
        capability_grant_id,
        executor_binding_id,
        tool_boundary_id,
        tool_name,
    )

    return {
        "tool_invocation_id": invocation_id,
        "runtime_session_id": session_id,
        "execution_lease_id": lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_binding_id": executor_binding_id,
        "tool_boundary_id": tool_boundary_id,
        "tool_name": tool_name,
        "invocation_status": "approved",
        "invocation_result": {
            "result_type": "synthetic_only",
            "produced_by": "runtime_tool_invocation_controller",
            "real_tool_executed": False,
            "value": None,
        },
        "failure_reason": None,
        "audit_projection": build_runtime_tool_invocation_audit_projection(
            {
                "tool_invocation_id": invocation_id,
                "runtime_session_id": session_id,
                "execution_lease_id": lease_id,
                "capability_grant_id": capability_grant_id,
                "executor_binding_id": executor_binding_id,
                "tool_boundary_id": tool_boundary_id,
                "tool_name": tool_name,
                "invocation_status": "approved",
                "invocation_result": {
                    "result_type": "synthetic_only",
                    "real_tool_executed": False,
                    "value": None,
                },
                "failure_reason": None,
            }
        ),
        "supported_states": list(TOOL_INVOCATION_STATES),
        "timeout_model": _as_mapping(record.get("timeout_model")),
        "cancellation_model": _as_mapping(record.get("cancellation_model")),
        "failure_ownership": _as_mapping(record.get("failure_ownership")),
        "record_only": True,
        "actual_tool_executed": False,
        "subprocess_allowed": False,
        "shell_allowed": False,
        "filesystem_access_allowed": False,
        "file_read_allowed": False,
        "file_write_allowed": False,
        "network_allowed": False,
        "mutation_allowed": False,
        "task_execution_allowed": False,
        "autonomy_allowed": False,
        "background_loop_allowed": False,
    }


def fail_runtime_tool_invocation(
    invocation_record: dict[str, Any],
    *,
    reason: str,
    owner: str = "runtime_tool_invocation_controller",
) -> dict[str, Any]:
    invocation = _as_mapping(invocation_record)
    ownership = _as_mapping(invocation.get("failure_ownership"))
    ownership["failure_owner"] = owner
    ownership["failure_recorded"] = True
    ownership["failure_reason"] = reason
    invocation["failure_ownership"] = ownership
    invocation["invocation_status"] = "failed"
    invocation["failure_reason"] = reason
    invocation["invocation_result"] = {
        "result_type": "synthetic_failure",
        "produced_by": owner,
        "real_tool_executed": False,
        "value": None,
    }
    invocation["actual_tool_executed"] = False
    invocation["audit_projection"] = build_runtime_tool_invocation_audit_projection(
        invocation
    )
    return invocation


def expire_runtime_tool_invocation(
    invocation_record: dict[str, Any],
    *,
    current_tick: int,
) -> dict[str, Any]:
    invocation = _as_mapping(invocation_record)
    timeout = _as_mapping(invocation.get("timeout_model"))
    timeout_at = timeout.get("timeout_at_tick", 0)
    timed_out = current_tick >= timeout_at
    timeout["current_tick"] = current_tick
    timeout["timed_out"] = timed_out
    if timed_out:
        invocation["invocation_status"] = "expired"
        invocation["failure_reason"] = "tool_invocation_expired"
    invocation["timeout_model"] = timeout
    invocation["actual_tool_executed"] = False
    invocation["audit_projection"] = build_runtime_tool_invocation_audit_projection(
        invocation
    )
    return invocation


def revoke_runtime_tool_invocation(
    invocation_record: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    invocation = _as_mapping(invocation_record)
    cancellation = _as_mapping(invocation.get("cancellation_model"))
    cancellation["cancelled"] = True
    cancellation["cancellation_reason"] = reason
    invocation["cancellation_model"] = cancellation
    invocation["invocation_status"] = "revoked"
    invocation["failure_reason"] = "tool_invocation_revoked"
    invocation["actual_tool_executed"] = False
    invocation["audit_projection"] = build_runtime_tool_invocation_audit_projection(
        invocation
    )
    return invocation


def can_runtime_tool_invocation_continue(
    invocation_record: dict[str, Any],
) -> dict[str, Any]:
    invocation = _as_mapping(invocation_record)
    status = invocation.get("invocation_status", "pending")
    if status == "expired":
        reason = "tool_invocation_expired"
    elif status == "revoked":
        reason = "tool_invocation_revoked"
    elif status == "failed":
        reason = "tool_invocation_failed"
    else:
        reason = "actual_tool_execution_disabled"

    return {
        "tool_invocation_id": invocation.get("tool_invocation_id"),
        "invocation_status": status,
        "can_continue": False,
        "blocked": True,
        "blocked_reason": reason,
        "actual_tool_execution_allowed": False,
        "subprocess_allowed": False,
        "shell_allowed": False,
        "filesystem_access_allowed": False,
        "network_allowed": False,
        "mutation_allowed": False,
        "task_execution_allowed": False,
    }


def build_runtime_tool_invocation_heartbeat_projection(
    invocation_record: dict[str, Any] | None,
) -> dict[str, Any]:
    invocation = _as_mapping(invocation_record)
    return {
        "projection": "runtime_tool_invocation_heartbeat",
        "projection_only": True,
        "tool_invocation_id": invocation.get("tool_invocation_id"),
        "runtime_session_id": invocation.get("runtime_session_id"),
        "execution_lease_id": invocation.get("execution_lease_id"),
        "capability_grant_id": invocation.get("capability_grant_id"),
        "executor_binding_id": invocation.get("executor_binding_id"),
        "tool_boundary_id": invocation.get("tool_boundary_id"),
        "tool_name": invocation.get("tool_name"),
        "invocation_status": invocation.get("invocation_status", "pending"),
        "heartbeat_live": False,
        "background_loop_allowed": False,
        "actual_tool_executed": False,
        "actual_tool_execution_allowed": False,
        "filesystem_access_allowed": False,
        "network_allowed": False,
        "mutation_allowed": False,
    }


def build_runtime_tool_invocation_audit_projection(
    invocation_record: dict[str, Any] | None,
) -> dict[str, Any]:
    invocation = _as_mapping(invocation_record)
    return {
        "projection": "runtime_tool_invocation_audit",
        "projection_only": True,
        "tool_invocation_id": invocation.get("tool_invocation_id"),
        "runtime_session_id": invocation.get("runtime_session_id"),
        "execution_lease_id": invocation.get("execution_lease_id"),
        "capability_grant_id": invocation.get("capability_grant_id"),
        "executor_binding_id": invocation.get("executor_binding_id"),
        "tool_boundary_id": invocation.get("tool_boundary_id"),
        "tool_name": invocation.get("tool_name"),
        "invocation_status": invocation.get("invocation_status", "pending"),
        "invocation_result": invocation.get("invocation_result"),
        "failure_reason": invocation.get("failure_reason"),
        "actual_tool_executed": False,
        "subprocess_started": False,
        "shell_started": False,
        "filesystem_access_performed": False,
        "network_performed": False,
        "mutation_performed": False,
        "task_executed": False,
        "autonomy_started": False,
        "background_loop_started": False,
    }


def build_runtime_tool_invocation_audit_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_runtime_tool_invocation_request(request)
    invocation = validation["tool_invocation_record"]

    return {
        "audit_schema": RUNTIME_TOOL_INVOCATION_CONTROLLER_SCHEMA + ".audit",
        "decision": "reserved_runtime_tool_invocation_record_only",
        "tool_invocation_request_id": validation.get("tool_invocation_request_id"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "tool_boundary_id": validation.get("tool_boundary_id"),
        "request_valid": validation["valid"],
        "invocation_created": validation["invocation_created"],
        "tool_invocation_record": invocation,
        "heartbeat_projection": build_runtime_tool_invocation_heartbeat_projection(
            invocation
        ),
        "audit_projection": build_runtime_tool_invocation_audit_projection(invocation),
        "actual_tool_executed": False,
        "subprocess_started": False,
        "shell_started": False,
        "filesystem_access_performed": False,
        "network_performed": False,
        "mutation_performed": False,
        "task_executed": False,
        "autonomy_started": False,
        "background_loop_started": False,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
        "non_mainline_issues": validation["problems"],
    }


def build_runtime_tool_invocation_milestone_seal(
    request: dict[str, Any],
) -> dict[str, Any]:
    audit = build_runtime_tool_invocation_audit_record(request)

    return {
        "seal": "runtime_tool_invocation_controller_bundle",
        "schema": RUNTIME_TOOL_INVOCATION_CONTROLLER_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_CONTROLLED_TOOL_CALL_LIFECYCLE_RECORD_ONLY_ZERO_REAL_EFFECTS",
        "next_package": 1257,
        "tool_invocation_request_id": audit.get("tool_invocation_request_id"),
        "runtime_session_id": audit.get("runtime_session_id"),
        "execution_lease_id": audit.get("execution_lease_id"),
        "capability_grant_id": audit.get("capability_grant_id"),
        "executor_binding_id": audit.get("executor_binding_id"),
        "tool_boundary_id": audit.get("tool_boundary_id"),
        "invocation_created": audit["invocation_created"],
        "audit_decision": audit["decision"],
        "actual_tool_executed": False,
        "subprocess_started": False,
        "shell_started": False,
        "filesystem_access_performed": False,
        "network_performed": False,
        "mutation_performed": False,
        "task_executed": False,
        "autonomy_started": False,
        "background_loop_started": False,
        "all_real_world_effects_locked": True,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


__all__ = [
    "RUNTIME_TOOL_INVOCATION_CONTROLLER_SCHEMA",
    "AUTHORIZED_TOOL_INVOCATION_DECISION",
    "TOOL_INVOCATION_STATES",
    "REQUIRED_TOOL_INVOCATION_FIELDS",
    "TOOL_INVOCATION_LOCKS",
    "REQUIRED_BLOCKERS",
    "build_runtime_tool_invocation_request",
    "validate_runtime_tool_invocation_request",
    "build_runtime_tool_invocation_record",
    "fail_runtime_tool_invocation",
    "expire_runtime_tool_invocation",
    "revoke_runtime_tool_invocation",
    "can_runtime_tool_invocation_continue",
    "build_runtime_tool_invocation_heartbeat_projection",
    "build_runtime_tool_invocation_audit_projection",
    "build_runtime_tool_invocation_audit_record",
    "build_runtime_tool_invocation_milestone_seal",
]
