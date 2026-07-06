from __future__ import annotations

from copy import deepcopy
from typing import Any


RUNTIME_CONTROLLED_TOOL_BOUNDARY_SCHEMA = "zero.runtime.controlled_tool_boundary.v1"

AUTHORIZED_TOOL_ADMISSION_DECISION = "AUTHORIZE_TOOL_ADMISSION_RECORD_ONLY"

TOOL_BOUNDARY_STATUSES = ("denied", "admitted", "expired", "revoked")

REQUESTED_TOOL_TYPES = (
    "read_tool",
    "write_tool",
    "command_tool",
    "network_tool",
    "mutation_tool",
    "recovery_tool",
)

REQUIRED_TOOL_BOUNDARY_FIELDS = (
    "tool_boundary_request_id",
    "runtime_session_id",
    "execution_lease",
    "capability_grant",
    "executor_binding",
    "requested_tool_name",
    "requested_tool_type",
    "authorization_input",
    "expiration_model",
    "revocation_model",
    "audit_required",
)

TOOL_BOUNDARY_LOCKS = {
    "tool_runtime_enabled": False,
    "tool_invocation_allowed": False,
    "subprocess_allowed": False,
    "shell_command_allowed": False,
    "file_read_allowed": False,
    "file_write_allowed": False,
    "network_allowed": False,
    "mutation_allowed": False,
    "task_execution_allowed": False,
    "autonomy_allowed": False,
    "self_start_allowed": False,
    "background_loop_allowed": False,
}

REQUIRED_BLOCKERS = (
    "runtime_session_id_required",
    "active_execution_lease_required",
    "active_capability_grant_required",
    "active_executor_binding_required",
    "explicit_tool_authorization_required",
    "tool_boundary_record_only",
    "all_tools_default_denied",
    "tool_invocation_locked",
    "subprocess_locked",
    "shell_command_locked",
    "file_read_locked",
    "file_write_locked",
    "network_locked",
    "mutation_locked",
    "task_execution_locked",
    "autonomy_locked",
    "self_start_locked",
    "background_loop_locked",
)


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _missing_required_fields(record: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_TOOL_BOUNDARY_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in TOOL_BOUNDARY_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def _tool_boundary_id(
    request_id: str,
    session_id: str,
    lease_id: str,
    capability_grant_id: str,
    executor_binding_id: str,
    requested_tool_name: str,
) -> str:
    return (
        f"tool-boundary::{session_id}::{lease_id}::{capability_grant_id}::"
        f"{executor_binding_id}::{requested_tool_name}::{request_id}"
    )


def build_runtime_controlled_tool_boundary_request(
    *,
    tool_boundary_request_id: str,
    runtime_session_id: str | None = None,
    execution_lease: dict[str, Any] | None = None,
    capability_grant: dict[str, Any] | None = None,
    executor_binding: dict[str, Any] | None = None,
    requested_tool_name: str | None = None,
    requested_tool_type: str = "read_tool",
    authorization_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_CONTROLLED_TOOL_BOUNDARY_SCHEMA,
        "tool_boundary_request_id": tool_boundary_request_id,
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
        "requested_tool_name": requested_tool_name,
        "requested_tool_type": requested_tool_type,
        "authorization_input": (
            deepcopy(authorization_input)
            if authorization_input is not None
            else {
                "decision": "NO_GO",
                "explicit_tool_authorization": False,
                "authorize_tool_admission_record": False,
            }
        ),
        "expiration_model": {
            "model": "deterministic_counter",
            "expires_at_tick": 1,
            "current_tick": 0,
            "expired": False,
        },
        "revocation_model": {
            "revocable": True,
            "revoked": False,
            "revocation_reason": None,
        },
        "boundary_locks": deepcopy(TOOL_BOUNDARY_LOCKS),
        "audit_required": True,
        "blockers": list(REQUIRED_BLOCKERS),
        "non_mainline_issue_reporting_required": True,
    }


def _evaluate_tool_boundary_request(record: dict[str, Any]) -> dict[str, Any]:
    session_id = record.get("runtime_session_id")
    lease = _as_mapping(record.get("execution_lease"))
    grant = _as_mapping(record.get("capability_grant"))
    binding = _as_mapping(record.get("executor_binding"))
    authorization = _as_mapping(record.get("authorization_input"))
    requested_tool_name = record.get("requested_tool_name")
    requested_tool_type = record.get("requested_tool_type")

    lease_id = lease.get("lease_id")
    capability_grant_id = grant.get("capability_grant_id")
    executor_binding_id = binding.get("executor_binding_id")

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
    authorized = (
        authorization.get("decision") == AUTHORIZED_TOOL_ADMISSION_DECISION
        and authorization.get("explicit_tool_authorization") is True
        and authorization.get("authorize_tool_admission_record") is True
    )

    denial_reasons: list[str] = []
    if not session_id:
        denial_reasons.append("invalid_runtime_session_id")
    if not active_lease:
        denial_reasons.append("inactive_execution_lease")
    if not active_grant:
        denial_reasons.append("inactive_capability_grant")
    if not active_binding:
        denial_reasons.append("inactive_executor_binding")
    if not requested_tool_name:
        denial_reasons.append("invalid_requested_tool_name")
    if requested_tool_type not in REQUESTED_TOOL_TYPES:
        denial_reasons.append("invalid_requested_tool_type")
    if not authorized:
        denial_reasons.append("tool_authorization_missing")

    return {
        "runtime_session_id": session_id,
        "execution_lease_id": lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_binding_id": executor_binding_id,
        "requested_tool_name": requested_tool_name,
        "requested_tool_type": requested_tool_type,
        "authorized": authorized,
        "admission_granted": not denial_reasons,
        "denial_reasons": denial_reasons,
        "denial_reason": "none" if not denial_reasons else ";".join(denial_reasons),
    }


def validate_runtime_controlled_tool_boundary_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    blockers = _as_list(record.get("blockers"))
    missing_blockers = [b for b in REQUIRED_BLOCKERS if b not in blockers]
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    evaluation = _evaluate_tool_boundary_request(record)

    structural_problems: list[str] = []
    if missing:
        structural_problems.append("missing_required_fields")
    if missing_blockers:
        structural_problems.append("missing_required_blockers")
    if unlocks:
        structural_problems.append("boundary_unlock_attempt")
    if record.get("audit_required") is not True:
        structural_problems.append("audit_not_required")
    if record.get("non_mainline_issue_reporting_required") is not True:
        structural_problems.append("non_mainline_issue_reporting_not_required")

    denial_reasons = list(evaluation["denial_reasons"])
    denial_reasons.extend(structural_problems)
    admission_granted = not denial_reasons
    boundary_record = build_runtime_controlled_tool_boundary_record(
        record,
        admission_granted=admission_granted,
        denial_reasons=denial_reasons,
    )

    return {
        "schema": RUNTIME_CONTROLLED_TOOL_BOUNDARY_SCHEMA,
        "valid": not structural_problems,
        "tool_boundary_request_id": record.get("tool_boundary_request_id"),
        "runtime_session_id": evaluation["runtime_session_id"],
        "execution_lease_id": evaluation["execution_lease_id"],
        "capability_grant_id": evaluation["capability_grant_id"],
        "executor_binding_id": evaluation["executor_binding_id"],
        "status": "accepted_tool_boundary_record_request",
        "problems": denial_reasons,
        "missing_required_fields": missing,
        "missing_required_blockers": missing_blockers,
        "unlock_attempts": unlocks,
        "tool_boundary_created": True,
        "admission_granted": admission_granted,
        "tool_boundary_record": boundary_record,
        "tool_runtime_enabled": False,
        "tool_invoked": False,
        "tool_invocation_allowed": False,
        "subprocess_started": False,
        "shell_command_started": False,
        "file_read_performed": False,
        "file_write_performed": False,
        "network_performed": False,
        "mutation_performed": False,
        "task_executed": False,
        "autonomy_started": False,
        "self_start_performed": False,
        "background_loop_started": False,
        "audit_required": True,
    }


def build_runtime_controlled_tool_boundary_record(
    request: dict[str, Any],
    *,
    admission_granted: bool | None = None,
    denial_reasons: list[str] | None = None,
) -> dict[str, Any]:
    record = _as_mapping(request)
    evaluation = _evaluate_tool_boundary_request(record)
    reasons = (
        list(denial_reasons)
        if denial_reasons is not None
        else list(evaluation["denial_reasons"])
    )
    granted = not reasons if admission_granted is None else admission_granted
    status = "admitted" if granted else "denied"
    session_id = str(evaluation["runtime_session_id"])
    lease_id = str(evaluation["execution_lease_id"])
    capability_grant_id = str(evaluation["capability_grant_id"])
    executor_binding_id = str(evaluation["executor_binding_id"])
    requested_tool_name = str(evaluation["requested_tool_name"])
    request_id = str(record.get("tool_boundary_request_id"))
    denial_reason = "none" if granted else ";".join(reasons)

    boundary_id = _tool_boundary_id(
        request_id,
        session_id,
        lease_id,
        capability_grant_id,
        executor_binding_id,
        requested_tool_name,
    )
    audit_projection = {
        "projection": "runtime_controlled_tool_boundary_audit",
        "projection_only": True,
        "tool_boundary_id": boundary_id,
        "tool_boundary_status": status,
        "admission_granted": granted,
        "denial_reason": denial_reason,
        "tool_invoked": False,
        "tool_invocation_allowed": False,
        "subprocess_allowed": False,
        "shell_command_allowed": False,
        "file_read_allowed": False,
        "file_write_allowed": False,
        "network_allowed": False,
        "mutation_allowed": False,
        "task_execution_allowed": False,
        "autonomy_allowed": False,
        "self_start_allowed": False,
        "background_loop_allowed": False,
    }

    return {
        "tool_boundary_id": boundary_id,
        "runtime_session_id": session_id,
        "execution_lease_id": lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_binding_id": executor_binding_id,
        "requested_tool_name": requested_tool_name,
        "requested_tool_type": evaluation["requested_tool_type"],
        "tool_boundary_status": status,
        "admission_granted": granted,
        "denial_reason": denial_reason,
        "audit_projection": audit_projection,
        "supported_statuses": list(TOOL_BOUNDARY_STATUSES),
        "supported_requested_tool_types": list(REQUESTED_TOOL_TYPES),
        "expiration_model": _as_mapping(record.get("expiration_model")),
        "revocation_model": _as_mapping(record.get("revocation_model")),
        "record_only": True,
        "tool_runtime_enabled": False,
        "tool_invoked": False,
        "tool_invocation_allowed": False,
        "subprocess_allowed": False,
        "shell_command_allowed": False,
        "file_read_allowed": False,
        "file_write_allowed": False,
        "network_allowed": False,
        "mutation_allowed": False,
        "task_execution_allowed": False,
        "autonomy_allowed": False,
        "self_start_allowed": False,
        "background_loop_allowed": False,
    }


def expire_runtime_controlled_tool_boundary(
    boundary_record: dict[str, Any],
    *,
    current_tick: int,
) -> dict[str, Any]:
    boundary = _as_mapping(boundary_record)
    expiration = _as_mapping(boundary.get("expiration_model"))
    expires_at = expiration.get("expires_at_tick", 0)
    expired = current_tick >= expires_at
    expiration["current_tick"] = current_tick
    expiration["expired"] = expired
    if expired:
        boundary["tool_boundary_status"] = "expired"
        boundary["admission_granted"] = False
        boundary["denial_reason"] = "tool_boundary_expired"
    boundary["expiration_model"] = expiration
    boundary["tool_invocation_allowed"] = False
    boundary["tool_runtime_enabled"] = False
    boundary["tool_invoked"] = False
    boundary["audit_projection"] = build_runtime_controlled_tool_audit_projection(
        boundary
    )
    return boundary


def revoke_runtime_controlled_tool_boundary(
    boundary_record: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    boundary = _as_mapping(boundary_record)
    revocation = _as_mapping(boundary.get("revocation_model"))
    revocation["revoked"] = True
    revocation["revocation_reason"] = reason
    boundary["revocation_model"] = revocation
    boundary["tool_boundary_status"] = "revoked"
    boundary["admission_granted"] = False
    boundary["denial_reason"] = "tool_boundary_revoked"
    boundary["tool_invocation_allowed"] = False
    boundary["tool_runtime_enabled"] = False
    boundary["tool_invoked"] = False
    boundary["audit_projection"] = build_runtime_controlled_tool_audit_projection(
        boundary
    )
    return boundary


def can_runtime_controlled_tool_boundary_authorize_invocation(
    boundary_record: dict[str, Any],
) -> dict[str, Any]:
    boundary = _as_mapping(boundary_record)
    status = boundary.get("tool_boundary_status", "denied")
    if status == "expired":
        reason = "tool_boundary_expired"
    elif status == "revoked":
        reason = "tool_boundary_revoked"
    elif status != "admitted":
        reason = boundary.get("denial_reason") or "tool_boundary_denied"
    else:
        reason = "tool_invocation_disabled"

    return {
        "tool_boundary_id": boundary.get("tool_boundary_id"),
        "tool_boundary_status": status,
        "admission_granted": bool(boundary.get("admission_granted", False)),
        "can_authorize_invocation": False,
        "blocked": True,
        "blocked_reason": reason,
        "tool_invocation_allowed": False,
        "subprocess_allowed": False,
        "shell_command_allowed": False,
        "file_read_allowed": False,
        "file_write_allowed": False,
        "network_allowed": False,
        "mutation_allowed": False,
        "task_execution_allowed": False,
    }


def build_runtime_controlled_tool_audit_projection(
    boundary_record: dict[str, Any] | None,
) -> dict[str, Any]:
    boundary = _as_mapping(boundary_record)
    return {
        "projection": "runtime_controlled_tool_boundary_audit",
        "projection_only": True,
        "tool_boundary_id": boundary.get("tool_boundary_id"),
        "runtime_session_id": boundary.get("runtime_session_id"),
        "execution_lease_id": boundary.get("execution_lease_id"),
        "capability_grant_id": boundary.get("capability_grant_id"),
        "executor_binding_id": boundary.get("executor_binding_id"),
        "requested_tool_name": boundary.get("requested_tool_name"),
        "requested_tool_type": boundary.get("requested_tool_type"),
        "tool_boundary_status": boundary.get("tool_boundary_status", "denied"),
        "admission_granted": bool(boundary.get("admission_granted", False)),
        "denial_reason": boundary.get("denial_reason", "default_denied"),
        "tool_invoked": False,
        "tool_runtime_enabled": False,
        "tool_invocation_allowed": False,
        "subprocess_allowed": False,
        "shell_command_allowed": False,
        "file_read_allowed": False,
        "file_write_allowed": False,
        "network_allowed": False,
        "mutation_allowed": False,
        "task_execution_allowed": False,
        "autonomy_allowed": False,
        "self_start_allowed": False,
        "background_loop_allowed": False,
    }


def build_runtime_controlled_tool_boundary_audit_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_runtime_controlled_tool_boundary_request(request)
    boundary = validation["tool_boundary_record"]

    return {
        "audit_schema": RUNTIME_CONTROLLED_TOOL_BOUNDARY_SCHEMA + ".audit",
        "decision": "reserved_runtime_controlled_tool_boundary_record_only",
        "tool_boundary_request_id": validation.get("tool_boundary_request_id"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "request_valid": validation["valid"],
        "tool_boundary_created": validation["tool_boundary_created"],
        "admission_granted": validation["admission_granted"],
        "tool_boundary_record": boundary,
        "audit_projection": build_runtime_controlled_tool_audit_projection(boundary),
        "tool_invoked": False,
        "subprocess_started": False,
        "shell_command_started": False,
        "file_read_performed": False,
        "file_write_performed": False,
        "network_performed": False,
        "mutation_performed": False,
        "task_executed": False,
        "autonomy_started": False,
        "self_start_performed": False,
        "background_loop_started": False,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
        "non_mainline_issues": validation["problems"],
    }


def build_runtime_controlled_tool_boundary_milestone_seal(
    request: dict[str, Any],
) -> dict[str, Any]:
    audit = build_runtime_controlled_tool_boundary_audit_record(request)

    return {
        "seal": "runtime_controlled_tool_boundary_bundle",
        "schema": RUNTIME_CONTROLLED_TOOL_BOUNDARY_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_TOOL_ADMISSION_BOUNDARY_RECORD_ONLY_ZERO_TOOL_INVOCATION",
        "next_package": 1249,
        "tool_boundary_request_id": audit.get("tool_boundary_request_id"),
        "runtime_session_id": audit.get("runtime_session_id"),
        "execution_lease_id": audit.get("execution_lease_id"),
        "capability_grant_id": audit.get("capability_grant_id"),
        "executor_binding_id": audit.get("executor_binding_id"),
        "tool_boundary_created": audit["tool_boundary_created"],
        "admission_granted": audit["admission_granted"],
        "audit_decision": audit["decision"],
        "tool_invoked": False,
        "subprocess_started": False,
        "shell_command_started": False,
        "file_read_performed": False,
        "file_write_performed": False,
        "network_performed": False,
        "mutation_performed": False,
        "task_executed": False,
        "autonomy_started": False,
        "self_start_performed": False,
        "background_loop_started": False,
        "all_tool_surfaces_locked": True,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


__all__ = [
    "RUNTIME_CONTROLLED_TOOL_BOUNDARY_SCHEMA",
    "AUTHORIZED_TOOL_ADMISSION_DECISION",
    "TOOL_BOUNDARY_STATUSES",
    "REQUESTED_TOOL_TYPES",
    "REQUIRED_TOOL_BOUNDARY_FIELDS",
    "TOOL_BOUNDARY_LOCKS",
    "REQUIRED_BLOCKERS",
    "build_runtime_controlled_tool_boundary_request",
    "validate_runtime_controlled_tool_boundary_request",
    "build_runtime_controlled_tool_boundary_record",
    "expire_runtime_controlled_tool_boundary",
    "revoke_runtime_controlled_tool_boundary",
    "can_runtime_controlled_tool_boundary_authorize_invocation",
    "build_runtime_controlled_tool_audit_projection",
    "build_runtime_controlled_tool_boundary_audit_record",
    "build_runtime_controlled_tool_boundary_milestone_seal",
]
