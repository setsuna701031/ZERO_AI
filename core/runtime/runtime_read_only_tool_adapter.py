from __future__ import annotations

from copy import deepcopy
from typing import Any


RUNTIME_READ_ONLY_TOOL_ADAPTER_SCHEMA = "zero.runtime.read_only_tool_adapter.v1"

READ_ADAPTER_STATUSES = ("denied", "planned", "expired", "revoked")

REQUIRED_READ_ADAPTER_FIELDS = (
    "read_adapter_request_id",
    "runtime_session_id",
    "execution_lease",
    "capability_grant",
    "executor_binding",
    "tool_boundary",
    "tool_invocation",
    "requested_resource",
    "resource_ownership",
    "read_scope_model",
    "expiration_model",
    "revocation_model",
    "audit_required",
)

READ_ADAPTER_LOCKS = {
    "file_open_allowed": False,
    "pathlib_read_allowed": False,
    "filesystem_access_allowed": False,
    "write_allowed": False,
    "mutation_allowed": False,
    "subprocess_allowed": False,
    "shell_allowed": False,
    "network_allowed": False,
    "task_execution_allowed": False,
    "autonomy_allowed": False,
    "background_loop_allowed": False,
}

REQUIRED_BLOCKERS = (
    "runtime_session_id_required",
    "active_execution_lease_required",
    "active_capability_grant_required",
    "active_executor_binding_required",
    "active_tool_boundary_required",
    "active_tool_invocation_required",
    "read_capability_required",
    "resource_ownership_required",
    "read_scope_required",
    "read_adapter_record_only",
    "synthetic_read_result_only",
    "file_open_locked",
    "pathlib_read_locked",
    "filesystem_access_locked",
    "write_locked",
    "mutation_locked",
    "subprocess_locked",
    "shell_locked",
    "network_locked",
    "task_execution_locked",
    "autonomy_locked",
    "background_loop_locked",
)


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _missing_required_fields(record: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_READ_ADAPTER_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in READ_ADAPTER_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def _read_adapter_id(
    request_id: str,
    session_id: str,
    lease_id: str,
    capability_grant_id: str,
    executor_binding_id: str,
    tool_boundary_id: str,
    tool_invocation_id: str,
    requested_resource: str,
) -> str:
    return (
        f"read-adapter::{session_id}::{lease_id}::{capability_grant_id}::"
        f"{executor_binding_id}::{tool_boundary_id}::{tool_invocation_id}::"
        f"{requested_resource}::{request_id}"
    )


def build_runtime_read_only_tool_adapter_request(
    *,
    read_adapter_request_id: str,
    runtime_session_id: str | None = None,
    execution_lease: dict[str, Any] | None = None,
    capability_grant: dict[str, Any] | None = None,
    executor_binding: dict[str, Any] | None = None,
    tool_boundary: dict[str, Any] | None = None,
    tool_invocation: dict[str, Any] | None = None,
    requested_resource: str | None = None,
    resource_ownership: dict[str, Any] | None = None,
    read_scope_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_READ_ONLY_TOOL_ADAPTER_SCHEMA,
        "read_adapter_request_id": read_adapter_request_id,
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
        "tool_invocation": (
            deepcopy(tool_invocation) if tool_invocation is not None else {}
        ),
        "requested_resource": requested_resource,
        "resource_ownership": (
            deepcopy(resource_ownership)
            if resource_ownership is not None
            else {
                "owner_session_id": runtime_session_id,
                "ownership_verified": False,
            }
        ),
        "read_scope_model": (
            deepcopy(read_scope_model)
            if read_scope_model is not None
            else {
                "scope_type": "dry_run_resource_reference",
                "resource_in_scope": False,
                "filesystem_resolution_allowed": False,
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
        "boundary_locks": deepcopy(READ_ADAPTER_LOCKS),
        "audit_required": True,
        "blockers": list(REQUIRED_BLOCKERS),
        "non_mainline_issue_reporting_required": True,
    }


def _evaluate_read_adapter_request(record: dict[str, Any]) -> dict[str, Any]:
    session_id = record.get("runtime_session_id")
    lease = _as_mapping(record.get("execution_lease"))
    grant = _as_mapping(record.get("capability_grant"))
    binding = _as_mapping(record.get("executor_binding"))
    boundary = _as_mapping(record.get("tool_boundary"))
    invocation = _as_mapping(record.get("tool_invocation"))
    ownership = _as_mapping(record.get("resource_ownership"))
    scope = _as_mapping(record.get("read_scope_model"))
    requested_resource = record.get("requested_resource")

    lease_id = lease.get("lease_id")
    capability_grant_id = grant.get("capability_grant_id")
    executor_binding_id = binding.get("executor_binding_id")
    tool_boundary_id = boundary.get("tool_boundary_id")
    tool_invocation_id = invocation.get("tool_invocation_id")
    granted = _as_mapping(grant.get("granted_capabilities"))

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
    active_boundary = (
        bool(tool_boundary_id)
        and boundary.get("runtime_session_id") == session_id
        and boundary.get("execution_lease_id") == lease_id
        and boundary.get("capability_grant_id") == capability_grant_id
        and boundary.get("executor_binding_id") == executor_binding_id
        and boundary.get("tool_boundary_status") == "admitted"
        and boundary.get("admission_granted") is True
        and boundary.get("requested_tool_type") == "read_tool"
    )
    active_invocation = (
        bool(tool_invocation_id)
        and invocation.get("runtime_session_id") == session_id
        and invocation.get("execution_lease_id") == lease_id
        and invocation.get("capability_grant_id") == capability_grant_id
        and invocation.get("executor_binding_id") == executor_binding_id
        and invocation.get("tool_boundary_id") == tool_boundary_id
        and invocation.get("invocation_status") == "approved"
    )
    read_capability = granted.get("read_access") is True
    ownership_verified = (
        ownership.get("owner_session_id") == session_id
        and ownership.get("ownership_verified") is True
    )
    resource_in_scope = (
        bool(requested_resource)
        and scope.get("resource_in_scope") is True
        and scope.get("filesystem_resolution_allowed") is False
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
    if not active_boundary:
        problems.append("inactive_tool_boundary")
    if not tool_invocation_id:
        problems.append("missing_tool_invocation")
    elif not active_invocation:
        problems.append("inactive_tool_invocation")
    if not read_capability:
        problems.append("read_capability_missing")
    if not requested_resource:
        problems.append("invalid_requested_resource")
    if not ownership_verified:
        problems.append("resource_ownership_unverified")
    if not resource_in_scope:
        problems.append("read_scope_invalid")

    return {
        "runtime_session_id": session_id,
        "execution_lease_id": lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_binding_id": executor_binding_id,
        "tool_boundary_id": tool_boundary_id,
        "tool_invocation_id": tool_invocation_id,
        "requested_resource": requested_resource,
        "problems": problems,
    }


def validate_runtime_read_only_tool_adapter_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    blockers = _as_list(record.get("blockers"))
    missing_blockers = [b for b in REQUIRED_BLOCKERS if b not in blockers]
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    evaluation = _evaluate_read_adapter_request(record)

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

    adapter_record = (
        build_runtime_read_only_tool_adapter_record(record)
        if not problems
        else None
    )

    return {
        "schema": RUNTIME_READ_ONLY_TOOL_ADAPTER_SCHEMA,
        "valid": not problems,
        "read_adapter_request_id": record.get("read_adapter_request_id"),
        "runtime_session_id": evaluation["runtime_session_id"],
        "execution_lease_id": evaluation["execution_lease_id"],
        "capability_grant_id": evaluation["capability_grant_id"],
        "executor_binding_id": evaluation["executor_binding_id"],
        "tool_boundary_id": evaluation["tool_boundary_id"],
        "tool_invocation_id": evaluation["tool_invocation_id"],
        "status": "accepted_read_adapter_plan_request" if not problems else "blocked",
        "problems": problems,
        "missing_required_fields": missing,
        "missing_required_blockers": missing_blockers,
        "unlock_attempts": unlocks,
        "read_adapter_created": adapter_record is not None,
        "read_adapter_record": adapter_record,
        "file_open_performed": False,
        "pathlib_read_performed": False,
        "filesystem_access_performed": False,
        "write_performed": False,
        "mutation_performed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "task_executed": False,
        "autonomy_started": False,
        "background_loop_started": False,
        "audit_required": True,
    }


def build_runtime_read_only_tool_adapter_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    evaluation = _evaluate_read_adapter_request(record)
    session_id = str(evaluation["runtime_session_id"])
    lease_id = str(evaluation["execution_lease_id"])
    capability_grant_id = str(evaluation["capability_grant_id"])
    executor_binding_id = str(evaluation["executor_binding_id"])
    tool_boundary_id = str(evaluation["tool_boundary_id"])
    tool_invocation_id = str(evaluation["tool_invocation_id"])
    requested_resource = str(evaluation["requested_resource"])
    request_id = str(record.get("read_adapter_request_id"))
    adapter_id = _read_adapter_id(
        request_id,
        session_id,
        lease_id,
        capability_grant_id,
        executor_binding_id,
        tool_boundary_id,
        tool_invocation_id,
        requested_resource,
    )

    read_result = {
        "result_type": "synthetic_read_plan_only",
        "resource_reference": requested_resource,
        "content": None,
        "filesystem_touched": False,
    }
    adapter = {
        "read_adapter_id": adapter_id,
        "runtime_session_id": session_id,
        "execution_lease_id": lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_binding_id": executor_binding_id,
        "tool_boundary_id": tool_boundary_id,
        "tool_invocation_id": tool_invocation_id,
        "requested_resource": requested_resource,
        "read_status": "planned",
        "read_result": read_result,
        "denial_reason": "none",
        "audit_projection": {},
        "supported_statuses": list(READ_ADAPTER_STATUSES),
        "resource_ownership": _as_mapping(record.get("resource_ownership")),
        "read_scope_model": _as_mapping(record.get("read_scope_model")),
        "expiration_model": _as_mapping(record.get("expiration_model")),
        "revocation_model": _as_mapping(record.get("revocation_model")),
        "record_only": True,
        "file_open_performed": False,
        "pathlib_read_performed": False,
        "filesystem_access_performed": False,
        "write_performed": False,
        "mutation_performed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "task_executed": False,
        "autonomy_started": False,
        "background_loop_started": False,
    }
    adapter["audit_projection"] = build_runtime_read_only_tool_adapter_audit_projection(
        adapter
    )
    return adapter


def expire_runtime_read_only_tool_adapter(
    read_adapter_record: dict[str, Any],
    *,
    current_tick: int,
) -> dict[str, Any]:
    adapter = _as_mapping(read_adapter_record)
    expiration = _as_mapping(adapter.get("expiration_model"))
    expires_at = expiration.get("expires_at_tick", 0)
    expired = current_tick >= expires_at
    expiration["current_tick"] = current_tick
    expiration["expired"] = expired
    if expired:
        adapter["read_status"] = "expired"
        adapter["denial_reason"] = "read_adapter_expired"
    adapter["expiration_model"] = expiration
    adapter["filesystem_access_performed"] = False
    adapter["audit_projection"] = build_runtime_read_only_tool_adapter_audit_projection(
        adapter
    )
    return adapter


def revoke_runtime_read_only_tool_adapter(
    read_adapter_record: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    adapter = _as_mapping(read_adapter_record)
    revocation = _as_mapping(adapter.get("revocation_model"))
    revocation["revoked"] = True
    revocation["revocation_reason"] = reason
    adapter["revocation_model"] = revocation
    adapter["read_status"] = "revoked"
    adapter["denial_reason"] = "read_adapter_revoked"
    adapter["filesystem_access_performed"] = False
    adapter["audit_projection"] = build_runtime_read_only_tool_adapter_audit_projection(
        adapter
    )
    return adapter


def build_runtime_read_only_tool_adapter_audit_projection(
    read_adapter_record: dict[str, Any] | None,
) -> dict[str, Any]:
    adapter = _as_mapping(read_adapter_record)
    return {
        "projection": "runtime_read_only_tool_adapter_audit",
        "projection_only": True,
        "read_adapter_id": adapter.get("read_adapter_id"),
        "runtime_session_id": adapter.get("runtime_session_id"),
        "execution_lease_id": adapter.get("execution_lease_id"),
        "capability_grant_id": adapter.get("capability_grant_id"),
        "executor_binding_id": adapter.get("executor_binding_id"),
        "tool_boundary_id": adapter.get("tool_boundary_id"),
        "tool_invocation_id": adapter.get("tool_invocation_id"),
        "requested_resource": adapter.get("requested_resource"),
        "read_status": adapter.get("read_status", "denied"),
        "read_result": adapter.get("read_result"),
        "denial_reason": adapter.get("denial_reason", "not_planned"),
        "file_open_performed": False,
        "pathlib_read_performed": False,
        "filesystem_access_performed": False,
        "write_performed": False,
        "mutation_performed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "task_executed": False,
        "autonomy_started": False,
        "background_loop_started": False,
    }


def build_runtime_read_only_tool_adapter_audit_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_runtime_read_only_tool_adapter_request(request)
    adapter = validation["read_adapter_record"]

    return {
        "audit_schema": RUNTIME_READ_ONLY_TOOL_ADAPTER_SCHEMA + ".audit",
        "decision": "reserved_runtime_read_only_tool_adapter_plan_record_only",
        "read_adapter_request_id": validation.get("read_adapter_request_id"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "tool_boundary_id": validation.get("tool_boundary_id"),
        "tool_invocation_id": validation.get("tool_invocation_id"),
        "request_valid": validation["valid"],
        "read_adapter_created": validation["read_adapter_created"],
        "read_adapter_record": adapter,
        "audit_projection": build_runtime_read_only_tool_adapter_audit_projection(
            adapter
        ),
        "file_open_performed": False,
        "pathlib_read_performed": False,
        "filesystem_access_performed": False,
        "write_performed": False,
        "mutation_performed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "task_executed": False,
        "autonomy_started": False,
        "background_loop_started": False,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
        "non_mainline_issues": validation["problems"],
    }


def build_runtime_read_only_tool_adapter_milestone_seal(
    request: dict[str, Any],
) -> dict[str, Any]:
    audit = build_runtime_read_only_tool_adapter_audit_record(request)

    return {
        "seal": "runtime_read_only_tool_adapter_bundle",
        "schema": RUNTIME_READ_ONLY_TOOL_ADAPTER_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_GOVERNED_READ_PLAN_ONLY_ZERO_FILESYSTEM_TOUCH",
        "next_package": 1265,
        "read_adapter_request_id": audit.get("read_adapter_request_id"),
        "runtime_session_id": audit.get("runtime_session_id"),
        "execution_lease_id": audit.get("execution_lease_id"),
        "capability_grant_id": audit.get("capability_grant_id"),
        "executor_binding_id": audit.get("executor_binding_id"),
        "tool_boundary_id": audit.get("tool_boundary_id"),
        "tool_invocation_id": audit.get("tool_invocation_id"),
        "read_adapter_created": audit["read_adapter_created"],
        "audit_decision": audit["decision"],
        "file_open_performed": False,
        "pathlib_read_performed": False,
        "filesystem_access_performed": False,
        "write_performed": False,
        "mutation_performed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "task_executed": False,
        "autonomy_started": False,
        "background_loop_started": False,
        "all_filesystem_surfaces_locked": True,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


__all__ = [
    "RUNTIME_READ_ONLY_TOOL_ADAPTER_SCHEMA",
    "READ_ADAPTER_STATUSES",
    "REQUIRED_READ_ADAPTER_FIELDS",
    "READ_ADAPTER_LOCKS",
    "REQUIRED_BLOCKERS",
    "build_runtime_read_only_tool_adapter_request",
    "validate_runtime_read_only_tool_adapter_request",
    "build_runtime_read_only_tool_adapter_record",
    "expire_runtime_read_only_tool_adapter",
    "revoke_runtime_read_only_tool_adapter",
    "build_runtime_read_only_tool_adapter_audit_projection",
    "build_runtime_read_only_tool_adapter_audit_record",
    "build_runtime_read_only_tool_adapter_milestone_seal",
]
